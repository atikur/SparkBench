// Deterministic passive tracker core. No image framework, hardware or model API.
import Foundation

struct TrackerPoint {
    var x: Double; var y: Double
    var array: [Double] { [x,y] }
}
struct TrackerImage {
    let width: Int; let height: Int; let rgba: [UInt8]; let gray: [Double]
    init(width:Int,height:Int,rgba:[UInt8]) {
        precondition(rgba.count==width*height*4)
        self.width=width;self.height=height;self.rgba=rgba
        self.gray=(0..<(width*height)).map { i in
            0.2126*Double(rgba[i*4])+0.7152*Double(rgba[i*4+1])+0.0722*Double(rgba[i*4+2])
        }
    }
    func luma(_ x:Int,_ y:Int)->Double { gray[y*width+x] }
    func bilinearLuma(_ x:Double,_ y:Double)->Double {
        let ix=Int(floor(x)),iy=Int(floor(y)),fx=x-Double(ix),fy=y-Double(iy)
        return (1-fy)*((1-fx)*luma(ix,iy)+fx*luma(ix+1,iy)) +
            fy*((1-fx)*luma(ix,iy+1)+fx*luma(ix+1,iy+1))
    }
}
struct TrackerSettings: Codable {
    // Optional stationary matte white patches, separate from registration edges.
    let exposure_reference_patches: [[Double]]?
    let white_reference_fraction: Double?
    // Opt-in only: legacy configurations retain the absolute body-displacement gate.
    let camera_registration: CameraRegistrationSettings?
    let patch_matching: String?
    let body_patch_radius: Int?
    let horn_roi: [Int]
    let pivot_hint: [Double]
    let body_patches: [[Double]]
    let search_pixels: Int
    let patch_radius: Int
    let maximum_body_shift_pixels: Double
    let maximum_patch_spread_pixels: Double
    let maximum_patch_error: Double
    let minimum_patch_texture: Double
    let minimum_white_luma: Double
    let maximum_white_chroma: Double
    let minimum_component_area: Int
    let maximum_component_area: Int
    let minimum_elongation: Double
    let pivot_search_pixels: Int
    let minimum_pivot_contrast: Double
    let minimum_horn_length: Double
    let maximum_horn_length: Double
    let minimum_focus_ratio: Double
    let minimum_focus_variance: Double
    let minimum_area_ratio: Double
    let maximum_area_ratio: Double
}
struct CameraRegistrationSettings: Codable {
    let background_patches: [[Double]]
    let patch_radius: Int?
    let maximum_shift_pixels: Double
    let model: String?
    let maximum_rotation_degrees: Double?
    let maximum_scale_change: Double?
}
struct BodyMatch {
    var exposureGains:[Double]=[]
    var shift=TrackerPoint(x:0,y:0)
    var errors:[Double]=[]
    var texture:[Double]=[]
    var spread=0.0
    var reasons:[String]=[]
    var cameraShift:TrackerPoint?=nil
    var residualShift:TrackerPoint?=nil
    var cameraErrors:[Double]=[]
    var cameraTexture:[Double]=[]
    var cameraSpread=0.0
    var patchShifts:[TrackerPoint]=[]
    var cameraTransform:[Double]?=nil
    var cameraModelResidual=0.0
    var rawSpread=0.0
    var integerPatchShifts:[TrackerPoint]=[]
}
struct HornObservation {
    var pivot:TrackerPoint?=nil
    var tip:TrackerPoint?=nil
    var area=0
    var elongation=0.0
    var contrast=0.0
    var focus=0.0
    var reasons:[String]=[]
}
struct TrackingObservation {
    var body:BodyMatch
    var horn:HornObservation
    var reasons:[String] { body.reasons+horn.reasons }
    var accepted:Bool { reasons.isEmpty && horn.pivot != nil && horn.tip != nil }
}

func meanAndVariance(_ values:[Double])->(Double,Double) {
    guard !values.isEmpty else { return (0,0) }
    let mean=values.reduce(0,+)/Double(values.count)
    return (mean,values.reduce(0){$0+($1-mean)*($1-mean)}/Double(values.count))
}
func median(_ values:[Double])->Double {
    let sorted=values.sorted(),n=sorted.count
    return n%2==1 ? sorted[n/2] : (sorted[n/2-1]+sorted[n/2])/2
}
func matchPatches(_ current:TrackerImage,_ reference:TrackerImage,_ settings:TrackerSettings,_ centers:[[Double]],radiusOverride:Int?=nil)->BodyMatch {
    var result=BodyMatch(),dxs:[Double]=[],dys:[Double]=[]
    let radius=radiusOverride ?? settings.patch_radius,bound=settings.search_pixels
    guard radius>=2,radius<=10,settings.patch_matching==nil || settings.patch_matching=="bilinear_subpixel" else {
        result.reasons.append("invalid_patch_matching_settings");return result
    }
    let subpixel=settings.patch_matching=="bilinear_subpixel",margin=subpixel ? 1 : 0
    var hitBoundary=false
    for center in centers {
        let cx=Int(center[0].rounded()),cy=Int(center[1].rounded())
        guard current.width==reference.width,current.height==reference.height,
              cx-radius-bound-margin>=0,cy-radius-bound-margin>=0,
              cx+radius+bound+margin<current.width,cy+radius+bound+margin<current.height else {
            result.reasons.append("body_patch_outside_image");return result
        }
        var template:[Double]=[]
        for y in -radius...radius { for x in -radius...radius { template.append(reference.luma(cx+x,cy+y)) } }
        result.texture.append(sqrt(meanAndVariance(template).1))
        var best=(dx:0,dy:0,error:Double.infinity)
        for dy in -bound...bound { for dx in -bound...bound {
            var error=0.0,index=0
            for y in -radius...radius { for x in -radius...radius {
                error += abs(current.luma(cx+x+dx,cy+y+dy)-template[index]);index += 1
            }}
            error /= Double(template.count)
            if error<best.error { best=(dx,dy,error) }
        }}
        result.integerPatchShifts.append(TrackerPoint(x:Double(best.dx),y:Double(best.dy)))
        if abs(best.dx)>=bound || abs(best.dy)>=bound { hitBoundary=true }
        var refined=(dx:Double(best.dx),dy:Double(best.dy),error:best.error)
        if subpixel && abs(best.dx)<bound && abs(best.dy)<bound {
            // Actual bilinear pixel costs, not smoothing or interpolation of the
            // output trace. Retain the integer match if no fractional cost wins.
            for sy in -3...3 { for sx in -3...3 {
                let dx=Double(best.dx)+Double(sx)*0.25,dy=Double(best.dy)+Double(sy)*0.25
                var error=0.0,index=0
                for y in -radius...radius { for x in -radius...radius {
                    error += abs(current.bilinearLuma(Double(cx+x)+dx,Double(cy+y)+dy)-template[index]);index += 1
                }}
                error /= Double(template.count)
                if error<refined.error { refined=(dx,dy,error) }
            }}
        }
        result.errors.append(refined.error);dxs.append(refined.dx);dys.append(refined.dy)
        result.patchShifts.append(TrackerPoint(x:refined.dx,y:refined.dy))
    }
    guard !dxs.isEmpty else { result.reasons.append("no_body_reference_patches");return result }
    result.shift=TrackerPoint(x:median(dxs),y:median(dys))
    result.spread=max(dxs.max()!-dxs.min()!,dys.max()!-dys.min()!)
    result.rawSpread=result.spread
    if result.texture.contains(where:{$0<settings.minimum_patch_texture}) { result.reasons.append("body_reference_low_texture") }
    if result.errors.contains(where:{$0>settings.maximum_patch_error}) { result.reasons.append("body_registration_error_or_occlusion") }
    if result.spread>settings.maximum_patch_spread_pixels { result.reasons.append("body_patch_disagreement") }
    if hitBoundary { result.reasons.append("body_search_boundary") }
    return result
}

// Least-squares similarity transform; every anchor participates, with no discarded
// outliers. Extra anchors constrain the fit, and residuals remain explicitly gated.
func similarityTransform(_ anchors:[[Double]],_ shifts:[TrackerPoint])->[Double]? {
    guard anchors.count==shifts.count,anchors.count>=4 else { return nil }
    let n=Double(anchors.count)
    let x=anchors.reduce(0){$0+$1[0]}/n,y=anchors.reduce(0){$0+$1[1]}/n
    let u=zip(anchors,shifts).reduce(0){$0+$1.0[0]+$1.1.x}/n
    let v=zip(anchors,shifts).reduce(0){$0+$1.0[1]+$1.1.y}/n
    var denominator=0.0,aa=0.0,bb=0.0
    for (p,d) in zip(anchors,shifts) {
        let dx=p[0]-x,dy=p[1]-y,du=p[0]+d.x-u,dv=p[1]+d.y-v
        denominator += dx*dx+dy*dy;aa += dx*du+dy*dv;bb += dx*dv-dy*du
    }
    guard denominator>1 else { return nil }
    let a=aa/denominator,b=bb/denominator
    return [a,-b,u-a*x+b*y,b,a,v-b*x-a*y]
}
func transformed(_ point:TrackerPoint,_ matrix:[Double])->TrackerPoint {
    TrackerPoint(x:matrix[0]*point.x+matrix[1]*point.y+matrix[2],y:matrix[3]*point.x+matrix[4]*point.y+matrix[5])
}

func matchBody(_ current:TrackerImage,_ reference:TrackerImage,_ settings:TrackerSettings)->BodyMatch {
    var result=matchPatches(current,reference,settings,settings.body_patches,radiusOverride:settings.body_patch_radius)
    guard let registration=settings.camera_registration else {
        if hypot(result.shift.x,result.shift.y)>settings.maximum_body_shift_pixels { result.reasons.append("body_moved") }
        return result
    }
    // Background anchors must be distinct, non-collinear and outside the servo
    // initialization regions. A body-only shift must never become camera motion.
    let anchors=registration.background_patches,r=settings.horn_roi
    let bounded=anchors.count>=3 && anchors.count<=8 && anchors.allSatisfy {
        $0.count==2 && $0.allSatisfy(\.isFinite)
    }
    var separated=bounded,area=0.0
    if bounded {
        let margin=Double(max(max(settings.patch_radius,settings.body_patch_radius ?? settings.patch_radius),registration.patch_radius ?? settings.patch_radius)+settings.search_pixels)
        for i in anchors.indices {
            let p=anchors[i]
            if p[0]>=Double(r[0])-margin && p[0]<=Double(r[0]+r[2])+margin &&
                p[1]>=Double(r[1])-margin && p[1]<=Double(r[1]+r[3])+margin { separated=false }
            for q in settings.body_patches+Array(anchors.prefix(i)) {
                if hypot(p[0]-q[0],p[1]-q[1])<=2*margin { separated=false }
            }
        }
        for i in 1..<(anchors.count-1) { for j in (i+1)..<anchors.count {
            area=max(area,abs((anchors[i][0]-anchors[0][0])*(anchors[j][1]-anchors[0][1]) -
                (anchors[j][0]-anchors[0][0])*(anchors[i][1]-anchors[0][1])))
        }}
    }
    guard separated,area>100,registration.maximum_shift_pixels.isFinite,
          registration.maximum_shift_pixels>0,registration.maximum_shift_pixels<Double(settings.search_pixels) else {
        result.reasons.append("invalid_independent_background_anchors");return result
    }
    let camera=matchPatches(current,reference,settings,anchors,radiusOverride:registration.patch_radius)
    result.cameraShift=camera.shift;result.cameraErrors=camera.errors
    result.cameraTexture=camera.texture;result.cameraSpread=camera.spread
    if registration.model=="similarity" {
        guard let rotationBound=registration.maximum_rotation_degrees,rotationBound.isFinite,rotationBound>0,rotationBound<=0.5,
              let scaleBound=registration.maximum_scale_change,scaleBound.isFinite,scaleBound>0,scaleBound<=0.01,
              let matrix=similarityTransform(anchors,camera.patchShifts),result.patchShifts.count==settings.body_patches.count else {
            result.reasons.append("invalid_bounded_camera_model");return result
        }
        result.cameraTransform=matrix
        result.reasons += camera.reasons.filter{$0 != "body_patch_disagreement"}.map{$0.replacingOccurrences(of:"body",with:"camera")}
        let scale=hypot(matrix[0],matrix[3]),rotation=abs(atan2(matrix[3],matrix[0])*180/Double.pi)
        if abs(scale-1)>scaleBound || rotation>rotationBound { result.reasons.append("camera_rotation_or_scale_exceeds_bound") }
        for (p,d) in zip(anchors,camera.patchShifts) {
            let q=transformed(TrackerPoint(x:p[0],y:p[1]),matrix)
            result.cameraModelResidual=max(result.cameraModelResidual,hypot(q.x-p[0]-d.x,q.y-p[1]-d.y))
        }
        if result.cameraModelResidual>settings.maximum_patch_spread_pixels { result.reasons.append("camera_model_residual_exceeds_bound") }
        let regions=settings.body_patches+[settings.pivot_hint]+[[Double(r[0]),Double(r[1])],[Double(r[0]+r[2]),Double(r[1])],[Double(r[0]),Double(r[1]+r[3])],[Double(r[0]+r[2]),Double(r[1]+r[3])]]
        if regions.contains(where:{p in
            let q=transformed(TrackerPoint(x:p[0],y:p[1]),matrix)
            return hypot(q.x-p[0],q.y-p[1])>registration.maximum_shift_pixels
        }) { result.reasons.append("camera_displacement_exceeds_bound") }
        var dxs:[Double]=[],dys:[Double]=[]
        for (p,d) in zip(settings.body_patches,result.patchShifts) {
            let q=transformed(TrackerPoint(x:p[0],y:p[1]),matrix)
            dxs.append(d.x-(q.x-p[0]));dys.append(d.y-(q.y-p[1]))
        }
        let residual=TrackerPoint(x:median(dxs),y:median(dys))
        result.residualShift=residual
        result.spread=max(dxs.max()!-dxs.min()!,dys.max()!-dys.min()!)
        result.reasons.removeAll{$0=="body_patch_disagreement"}
        if result.spread>settings.maximum_patch_spread_pixels { result.reasons.append("body_patch_disagreement") }
        if hypot(residual.x,residual.y)>settings.maximum_body_shift_pixels { result.reasons.append("body_moved_relative_to_background") }
        let hint=TrackerPoint(x:settings.pivot_hint[0],y:settings.pivot_hint[1]),projected=transformed(hint,matrix)
        result.cameraShift=TrackerPoint(x:projected.x-hint.x,y:projected.y-hint.y)
        result.shift=TrackerPoint(x:projected.x-hint.x+residual.x,y:projected.y-hint.y+residual.y)
        return result
    }
    if registration.model != nil && registration.model != "translation" { result.reasons.append("unsupported_camera_model") }
    result.reasons += camera.reasons.map{$0.replacingOccurrences(of:"body",with:"camera")}
    if hypot(camera.shift.x,camera.shift.y)>registration.maximum_shift_pixels { result.reasons.append("camera_displacement_exceeds_bound") }
    let residual=TrackerPoint(x:result.shift.x-camera.shift.x,y:result.shift.y-camera.shift.y)
    result.residualShift=residual
    if hypot(residual.x,residual.y)>settings.maximum_body_shift_pixels { result.reasons.append("body_moved_relative_to_background") }
    return result
}

func focusVariance(_ image:TrackerImage,_ roi:[Int])->Double {
    var values:[Double]=[]
    for y in (roi[1]+1)..<(roi[1]+roi[3]-1) { for x in (roi[0]+1)..<(roi[0]+roi[2]-1) {
        values.append(image.luma(x-1,y)+image.luma(x+1,y)+image.luma(x,y-1)+image.luma(x,y+1)-4*image.luma(x,y))
    }}
    return meanAndVariance(values).1
}

func observeHorn(_ image:TrackerImage,_ settings:TrackerSettings,_ shift:TrackerPoint)->HornObservation {
    var result=HornObservation()
    var whiteThreshold=settings.minimum_white_luma
    if let fraction=settings.white_reference_fraction {
        guard fraction.isFinite,fraction>=0.7,fraction<=0.85,
              let patches=settings.exposure_reference_patches,patches.count>=4,patches.count<=8 else {
            result.reasons.append("invalid_white_reference");return result
        }
        var levels:[Double]=[]
        for p in patches {
            guard p.count==2,p.allSatisfy(\.isFinite),p[0]>=4,p[1]>=4,
                  p[0]<Double(image.width-4),p[1]<Double(image.height-4) else {
                result.reasons.append("invalid_white_reference");return result
            }
            var values:[Double]=[]
            let cx=Int(p[0].rounded()),cy=Int(p[1].rounded())
            for y in (cy-3)...(cy+3) { for x in (cx-3)...(cx+3) { values.append(image.luma(x,y)) } }
            let (level,variance)=meanAndVariance(values)
            guard level>=100,level<=245,variance<=64 else {
                result.reasons.append("invalid_white_reference");return result
            }
            levels.append(level)
        }
        whiteThreshold=median(levels)*fraction
    }
    let roi=[settings.horn_roi[0]+Int(shift.x.rounded()),settings.horn_roi[1]+Int(shift.y.rounded()),settings.horn_roi[2],settings.horn_roi[3]]
    guard roi[0]>0,roi[1]>0,roi[2]>20,roi[3]>20,roi[0]+roi[2]<image.width,roi[1]+roi[3]<image.height else {
        result.reasons.append("horn_roi_outside_image");return result
    }
    result.focus=focusVariance(image,roi)
    let w=roi[2],h=roi[3]
    let hint=TrackerPoint(x:settings.pivot_hint[0]+shift.x-Double(roi[0]),y:settings.pivot_hint[1]+shift.y-Double(roi[1]))
    var mask=[Bool](repeating:false,count:w*h)
    for y in 0..<h { for x in 0..<w {
        let gx=roi[0]+x,gy=roi[1]+y,i=(gy*image.width+gx)*4
        let rgb=[Double(image.rgba[i]),Double(image.rgba[i+1]),Double(image.rgba[i+2])]
        mask[y*w+x]=image.luma(gx,gy)>=whiteThreshold && rgb.max()!-rgb.min()!<=settings.maximum_white_chroma
    }}
    var seen=[Bool](repeating:false,count:w*h),candidates:[[Int]]=[]
    for start in mask.indices where mask[start] && !seen[start] {
        var queue=[start],cursor=0,nearHint=0
        seen[start]=true
        while cursor<queue.count {
            let p=queue[cursor];cursor += 1
            let x=p%w,y=p/w
            if hypot(Double(x)-hint.x,Double(y)-hint.y)<=12 { nearHint += 1 }
            for (nx,ny) in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)] where nx>=0 && ny>=0 && nx<w && ny<h {
                let i=ny*w+nx
                if mask[i] && !seen[i] { seen[i]=true;queue.append(i) }
            }
        }
        if nearHint>=20 && queue.count>=100 { candidates.append(queue) }
    }
    guard candidates.count==1 else { result.reasons.append(candidates.isEmpty ? "horn_component_missing" : "horn_component_ambiguous");return result }
    let component=candidates[0]
    result.area=component.count
    guard component.count>=settings.minimum_component_area,component.count<=settings.maximum_component_area else {
        result.reasons.append("horn_area_out_of_bounds");return result
    }
    guard !component.contains(where:{$0%w<=1 || $0%w>=w-2 || $0/w<=1 || $0/w>=h-2}) else {
        result.reasons.append("horn_component_clipped");return result
    }
    // Fill enclosed mask holes for geometry; retain original intensities for pivot detection.
    var filled=[Bool](repeating:false,count:w*h)
    for p in component { filled[p]=true }
    var outside=[Bool](repeating:false,count:w*h),flood:[Int]=[]
    for y in 0..<h { for x in 0..<w where x==0 || y==0 || x==w-1 || y==h-1 {
        let p=y*w+x
        if !filled[p] && !outside[p] { outside[p]=true;flood.append(p) }
    }}
    var cursor=0
    while cursor<flood.count {
        let p=flood[cursor];cursor += 1
        for (x,y) in [(p%w-1,p/w),(p%w+1,p/w),(p%w,p/w-1),(p%w,p/w+1)] where x>=0 && y>=0 && x<w && y<h {
            let q=y*w+x
            if !filled[q] && !outside[q] { outside[q]=true;flood.append(q) }
        }
    }
    for p in filled.indices where !outside[p] { filled[p]=true }
    // Detect the darker central hub feature within a manually initialized neighborhood.
    var best=(x:0,y:0,contrast:-Double.infinity,outer:0.0)
    let search=settings.pivot_search_pixels
    for cy in (Int(hint.y)-search)...(Int(hint.y)+search) { for cx in (Int(hint.x)-search)...(Int(hint.x)+search) {
        if cx<11 || cy<11 || cx>=w-11 || cy>=h-11 || hypot(Double(cx)-hint.x,Double(cy)-hint.y)>Double(search) { continue }
        var inner=0.0,outer=0.0,ni=0,no=0,inside=0
        for dy in -10...10 { for dx in -10...10 {
            let radius=dx*dx+dy*dy
            if radius<=9 { inner += image.luma(roi[0]+cx+dx,roi[1]+cy+dy);ni += 1 }
            if radius>=49 && radius<=100 {
                outer += image.luma(roi[0]+cx+dx,roi[1]+cy+dy);no += 1
                if filled[(cy+dy)*w+cx+dx] { inside += 1 }
            }
        }}
        if Double(inside)/Double(no)<0.97 { continue }
        let contrast=outer/Double(no)-inner/Double(ni)
        if contrast>best.contrast { best=(cx,cy,contrast,outer/Double(no)) }
    }}
    result.contrast=best.contrast.isFinite ? best.contrast : 0
    guard result.contrast>=settings.minimum_pivot_contrast else { result.reasons.append("pivot_not_resolved_or_blurred");return result }
    var weight=0.0,cx=0.0,cy=0.0
    for dy in -5...5 { for dx in -5...5 where dx*dx+dy*dy<=25 {
        let value=max(0,best.outer-image.luma(roi[0]+best.x+dx,roi[1]+best.y+dy))
        weight += value;cx += value*Double(best.x+dx);cy += value*Double(best.y+dy)
    }}
    guard weight>0 else { result.reasons.append("pivot_not_resolved_or_blurred");return result }
    let pivot=TrackerPoint(x:cx/weight,y:cy/weight)
    // Principal axis of the white silhouette; direction comes from hub-to-centroid.
    let points=filled.indices.filter{filled[$0]}.map{TrackerPoint(x:Double($0%w),y:Double($0/w))}
    let mx=points.reduce(0){$0+$1.x}/Double(points.count),my=points.reduce(0){$0+$1.y}/Double(points.count)
    let xx=points.reduce(0){$0+($1.x-mx)*($1.x-mx)}/Double(points.count)
    let yy=points.reduce(0){$0+($1.y-my)*($1.y-my)}/Double(points.count)
    let xy=points.reduce(0){$0+($1.x-mx)*($1.y-my)}/Double(points.count)
    let root=sqrt((xx-yy)*(xx-yy)+4*xy*xy)
    result.elongation=(xx+yy+root)/max(1e-9,xx+yy-root)
    guard result.elongation>=settings.minimum_elongation else { result.reasons.append("horn_direction_ambiguous");return result }
    let angle=0.5*atan2(2*xy,xx-yy)
    var ux=cos(angle),uy=sin(angle)
    let toward=(mx-pivot.x)*ux+(my-pivot.y)*uy
    if toward<0 { ux = -ux;uy = -uy }
    guard abs(toward)>=10 else { result.reasons.append("horn_direction_ambiguous");return result }
    let projected=points.map{(($0.x-pivot.x)*ux+($0.y-pivot.y)*uy,$0)}.sorted{$0.0>$1.0}
    let count=max(5,Int(Double(projected.count)*0.025))
    let cap=Array(projected.prefix(count))
    let tip=TrackerPoint(x:cap.reduce(0){$0+$1.1.x}/Double(cap.count),y:cap.reduce(0){$0+$1.1.y}/Double(cap.count))
    let length=hypot(tip.x-pivot.x,tip.y-pivot.y)
    guard length>=settings.minimum_horn_length,length<=settings.maximum_horn_length else { result.reasons.append("horn_length_out_of_bounds");return result }
    result.pivot=TrackerPoint(x:pivot.x+Double(roi[0]),y:pivot.y+Double(roi[1]))
    result.tip=TrackerPoint(x:tip.x+Double(roi[0]),y:tip.y+Double(roi[1]))
    return result
}

// Correct only bounded, spatially consistent RGB gain changes. Every patch must
// remain flat, unclipped and bright; no local horn-derived adjustment is allowed.
// A failed photometric reference rejects the frame rather than adapting limits.
func exposureCorrected(_ image:TrackerImage,_ reference:TrackerImage,_ settings:TrackerSettings)->(TrackerImage,[Double],[String]) {
    guard let patches=settings.exposure_reference_patches else { return (image,[],[]) }
    func invalid()->(TrackerImage,[Double],[String]) { (image,[],["exposure_reference_unavailable_or_inconsistent"]) }
    guard image.width==reference.width,image.height==reference.height,patches.count>=4,patches.count<=8 else { return invalid() }
    var ratios=[[Double]](repeating:[],count:3)
    let r=settings.horn_roi
    for (index,p) in patches.enumerated() {
        guard p.count==2,p.allSatisfy(\.isFinite),p[0]>=4,p[1]>=4,
              p[0]<Double(image.width-4),p[1]<Double(image.height-4),
              !(p[0]>=Double(r[0]-12) && p[0]<=Double(r[0]+r[2]+12) && p[1]>=Double(r[1]-12) && p[1]<=Double(r[1]+r[3]+12)),
              (settings.body_patches+Array(patches.prefix(index))).allSatisfy({hypot(p[0]-$0[0],p[1]-$0[1])>24}) else { return invalid() }
        let cx=Int(p[0].rounded()),cy=Int(p[1].rounded())
        for c in 0..<3 {
            var a:[Double]=[],b:[Double]=[]
            for y in (cy-3)...(cy+3) { for x in (cx-3)...(cx+3) {
                a.append(Double(reference.rgba[(y*image.width+x)*4+c]));b.append(Double(image.rgba[(y*image.width+x)*4+c]))
            }}
            let (am,av)=meanAndVariance(a),(bm,bv)=meanAndVariance(b)
            guard am>=100,am<=245,bm>=80,bm<=245,av<=64,bv<=64,
                  a.allSatisfy({$0>0 && $0<255}),b.allSatisfy({$0>0 && $0<255}) else { return invalid() }
            let gain=am/bm
            guard gain>=0.8,gain<=1.3 else { return invalid() }
            ratios[c].append(gain)
        }
    }
    guard ratios.allSatisfy({$0.max()!-$0.min()!<=0.04}) else { return invalid() }
    let gains=ratios.map{median($0)}
    var bytes=image.rgba
    for i in 0..<(image.width*image.height) { for c in 0..<3 {
        bytes[i*4+c]=UInt8(min(255,(Double(bytes[i*4+c])*gains[c]).rounded()))
    }}
    return (TrackerImage(width:image.width,height:image.height,rgba:bytes),gains,[])
}

func track(_ rawImage:TrackerImage,_ reference:TrackerImage,_ baseline:HornObservation,_ settings:TrackerSettings)->TrackingObservation {
    let (image,gains,exposureReasons)=exposureCorrected(rawImage,reference,settings)
    var body=matchBody(image,reference,settings)
    body.exposureGains=gains;body.reasons += exposureReasons
    var horn=observeHorn(image,settings,body.shift)
    if horn.focus<max(settings.minimum_focus_variance,baseline.focus*settings.minimum_focus_ratio) { horn.reasons.append("blur_or_low_detail") }
    if baseline.area>0 && (Double(horn.area)<Double(baseline.area)*settings.minimum_area_ratio || Double(horn.area)>Double(baseline.area)*settings.maximum_area_ratio) { horn.reasons.append("horn_area_changed_or_occluded") }
    if !body.reasons.isEmpty || !horn.reasons.isEmpty { horn.pivot=nil;horn.tip=nil }
    return TrackingObservation(body:body,horn:horn)
}
