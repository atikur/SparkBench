// Saved-image runner and clearly labeled digital controls. No camera/serial APIs.
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import CoreText

struct SavedFrame:Decodable { let id:String;let path:String }
struct TrackingRequest:Decodable {
    let reference_frame:String;let frames:[SavedFrame]
    let settings:TrackerSettings;let overlay_roi:[Int];let digital_controls:Bool
    let recorded_motion_analysis:Bool?
}
func fail(_ message:String)->Never { fputs(message+"\n",stderr);exit(2) }
func image(_ path:String)->TrackerImage {
    guard let source=CGImageSourceCreateWithURL(URL(fileURLWithPath:path) as CFURL,nil),
          let cg=CGImageSourceCreateImageAtIndex(source,0,nil),cg.width<=4096,cg.height<=4096 else { fail("Unsupported source image") }
    var rgba=[UInt8](repeating:0,count:cg.width*cg.height*4)
    rgba.withUnsafeMutableBytes { bytes in
        guard let context=CGContext(data:bytes.baseAddress,width:cg.width,height:cg.height,bitsPerComponent:8,bytesPerRow:cg.width*4,
            space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { fail("Cannot decode RGB pixels") }
        context.draw(cg,in:CGRect(x:0,y:0,width:cg.width,height:cg.height))
    }
    return TrackerImage(width:cg.width,height:cg.height,rgba:rgba)
}
func json(_ observation:TrackingObservation)->[String:Any] {
    ["status":observation.accepted ? "tracked_unverified" : "unknown",
     "reasons":observation.reasons,"pivot_px":observation.horn.pivot?.array as Any? ?? NSNull(),
     "tip_px":observation.horn.tip?.array as Any? ?? NSNull(),
     "quality":["body_shift_pixels":observation.body.shift.array,"body_patch_errors":observation.body.errors,
        "exposure_rgb_gains":observation.body.exposureGains,
        "camera_shift_pixels":observation.body.cameraShift?.array as Any? ?? NSNull(),
        "body_residual_shift_pixels":observation.body.residualShift?.array as Any? ?? NSNull(),
        "camera_patch_errors":observation.body.cameraErrors,"camera_patch_texture_stddev":observation.body.cameraTexture,
        "camera_patch_spread_pixels":observation.body.cameraSpread,
        "camera_image_transform":observation.body.cameraTransform as Any? ?? NSNull(),
        "camera_model_residual_pixels":observation.body.cameraModelResidual,
        "body_raw_patch_spread_pixels":observation.body.rawSpread,
        "body_patch_shifts_pixels":observation.body.patchShifts.map{$0.array},
        "body_integer_patch_shifts_pixels":observation.body.integerPatchShifts.map{$0.array},
        "body_patch_texture_stddev":observation.body.texture,"body_patch_spread_pixels":observation.body.spread,
        "horn_component_area":observation.horn.area,"horn_elongation":observation.horn.elongation,
        "pivot_contrast":observation.horn.contrast,"focus_laplacian_variance":observation.horn.focus],
     "angle_deg":NSNull(),"eligible_for_verifier":false]
}
func save(_ value:Any,_ path:URL) throws {
    guard !FileManager.default.fileExists(atPath:path.path) else { fail("Existing output rejected") }
    try JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys]).write(to:path)
}
func cgImage(_ image:TrackerImage)->CGImage {
    let data=Data(image.rgba)
    guard let provider=CGDataProvider(data:data as CFData),let cg=CGImage(width:image.width,height:image.height,bitsPerComponent:8,bitsPerPixel:32,
        bytesPerRow:image.width*4,space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGBitmapInfo(rawValue:CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue),provider:provider,decode:nil,shouldInterpolate:false,intent:.defaultIntent) else { fail("Cannot render RGB image") }
    return cg
}
func overlay(_ image:TrackerImage,_ observation:TrackingObservation,_ roi:[Int],_ output:URL,_ control:Bool=false,_ recordedMotion:Bool=false) {
    guard let crop=cgImage(image).cropping(to:CGRect(x:roi[0],y:roi[1],width:roi[2],height:roi[3])),
          let context=CGContext(data:nil,width:roi[2],height:roi[3]+48,bitsPerComponent:8,bytesPerRow:roi[2]*4,
            space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue) else { fail("Cannot draw tracking overlay") }
    context.draw(crop,in:CGRect(x:0,y:0,width:roi[2],height:roi[3]))
    func local(_ p:TrackerPoint)->CGPoint { CGPoint(x:p.x-Double(roi[0]),y:Double(roi[3])-(p.y-Double(roi[1]))) }
    if observation.accepted,let pivot=observation.horn.pivot,let tip=observation.horn.tip {
        context.setStrokeColor(CGColor(red:0,green:1,blue:0.5,alpha:1));context.setLineWidth(2)
        context.move(to:local(pivot));context.addLine(to:local(tip));context.strokePath()
        for p in [pivot,tip] { let c=local(p);context.strokeEllipse(in:CGRect(x:c.x-4,y:c.y-4,width:8,height:8)) }
    }
    context.setFillColor(CGColor(gray:0,alpha:0.95));context.fill(CGRect(x:0,y:roi[3],width:roi[2],height:48))
    let lines=[control ? "DIGITAL CONTROL - NOT PHYSICAL" : "AUTOMATIC PIXELS - UNVERIFIED",
        observation.accepted ? "Preview only; no true shaft angle" : "UNKNOWN - no carried-forward angle",
        observation.reasons.first ?? (recordedMotion ? "Saved motion; accuracy unqualified" : "Static tracking; accuracy unqualified")]
    for (index,line) in lines.enumerated() {
        let attrs:[NSAttributedString.Key:Any]=[
            NSAttributedString.Key(kCTFontAttributeName as String):CTFontCreateWithName("Menlo-Bold" as CFString,8,nil),
            NSAttributedString.Key(kCTForegroundColorAttributeName as String):CGColor(gray:1,alpha:1)]
        context.textPosition=CGPoint(x:4,y:roi[3]+36-index*13)
        CTLineDraw(CTLineCreateWithAttributedString(NSAttributedString(string:line,attributes:attrs)),context)
    }
    guard let cg=context.makeImage(),let destination=CGImageDestinationCreateWithURL(output as CFURL,UTType.png.identifier as CFString,1,nil) else { fail("Cannot save overlay") }
    CGImageDestinationAddImage(destination,cg,nil)
    guard CGImageDestinationFinalize(destination) else { fail("Overlay write failed") }
}

func modified(_ reference:TrackerImage,_ settings:TrackerSettings,_ baseline:HornObservation,_ kind:String,_ bodyROI:[Int])->TrackerImage {
    var bytes=reference.rgba
    func paint(_ x:Int,_ y:Int,_ value:UInt8) {
        guard x>=0,y>=0,x<reference.width,y<reference.height else { return }
        let p=(y*reference.width+x)*4;bytes[p]=value;bytes[p+1]=value;bytes[p+2]=value
    }
    let r=settings.horn_roi
    if kind=="occluded_horn" || kind=="partial_horn_occlusion" {
        for y in r[1]..<(r[1]+r[3]) { for x in r[0]..<(r[0]+r[2]) {
            var cover=kind=="occluded_horn"
            if let p=baseline.pivot,let t=baseline.tip {
                let dx=t.x-p.x,dy=t.y-p.y,length=hypot(dx,dy)
                cover = cover || ((Double(x)-p.x)*dx+(Double(y)-p.y)*dy)/length>length*0.35
            }
            if cover { paint(x,y,20) }
        }}
    } else if kind=="body_shift" {
        let shift=5
        for y in bodyROI[1]..<(bodyROI[1]+bodyROI[3]) { for x in bodyROI[0]..<(bodyROI[0]+bodyROI[2]+shift) { paint(x,y,25) } }
        for y in bodyROI[1]..<(bodyROI[1]+bodyROI[3]) { for x in bodyROI[0]..<(bodyROI[0]+bodyROI[2]) {
            let from=(y*reference.width+x)*4,to=(y*reference.width+x+shift)*4
            for c in 0..<4 { bytes[to+c]=reference.rgba[from+c] }
        }}
    } else if kind=="body_patch_occlusion" {
        for p in settings.body_patches {
            for y in (Int(p[1])-9)...(Int(p[1])+9) { for x in (Int(p[0])-9)...(Int(p[0])+9) { paint(x,y,0) } }
        }
    } else if kind=="camera_shift_exceeds_bound" {
        for y in 0..<reference.height { for x in 0..<reference.width {
            for c in 0..<4 { bytes[(y*reference.width+x)*4+c]=x>=5 ? reference.rgba[(y*reference.width+x-5)*4+c] : 25 }
        }}
    } else if kind=="background_patch_occlusion" || kind=="background_patch_disagreement" {
        if let registration=settings.camera_registration {
            for (index,p) in registration.background_patches.enumerated() {
                if kind=="background_patch_disagreement" && index>0 { continue }
                for y in (Int(p[1])-12)...(Int(p[1])+12) { for x in (Int(p[0])-12)...(Int(p[0])+12) {
                    if kind=="background_patch_occlusion" { paint(x,y,0) }
                    else {
                        for c in 0..<4 { bytes[(y*reference.width+x)*4+c]=reference.rgba[(y*reference.width+x-5)*4+c] }
                    }
                }}
            }
        }
    } else if kind=="blurred_horn" {
        // Three separable box passes, restricted to horn ROI. Deterministic derived control.
        for _ in 0..<3 { for horizontal in [true,false] {
            let source=bytes,radius=5
            for y in r[1]..<(r[1]+r[3]) { for x in r[0]..<(r[0]+r[2]) { for c in 0..<3 {
                var sum=0
                for k in -radius...radius {
                    let sx=max(r[0],min(r[0]+r[2]-1,x+(horizontal ? k : 0)))
                    let sy=max(r[1],min(r[1]+r[3]-1,y+(horizontal ? 0 : k)))
                    sum += Int(source[(sy*reference.width+sx)*4+c])
                }
                bytes[(y*reference.width+x)*4+c]=UInt8(sum/(2*radius+1))
            }}}
        }}
    }
    return TrackerImage(width:reference.width,height:reference.height,rgba:bytes)
}

guard CommandLine.arguments.count==3 else { fail("Expected REQUEST NEW_OUTPUT_DIRECTORY") }
let request=try JSONDecoder().decode(TrackingRequest.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
let output=URL(fileURLWithPath:CommandLine.arguments[2],isDirectory:true)
guard !FileManager.default.fileExists(atPath:output.path) else { fail("Existing evidence rejected") }
let s=request.settings
guard s.horn_roi.count==4,s.pivot_hint.count==2,s.body_patches.count>=3,s.body_patches.count<=8,s.body_patches.allSatisfy({$0.count==2}),
      s.search_pixels>=1,s.search_pixels<=16,s.patch_radius>=2,s.patch_radius<=10,s.pivot_search_pixels>=1,s.pivot_search_pixels<=24,
      request.overlay_roi.count==4 else { fail("Invalid bounded tracker settings") }
try FileManager.default.createDirectory(at:output,withIntermediateDirectories:true)
let reference=image(request.reference_frame)
let baseline=observeHorn(reference,s,TrackerPoint(x:0,y:0))
try save(["reasons":baseline.reasons,"component_area":baseline.area,"elongation":baseline.elongation,
          "pivot_contrast":baseline.contrast,"focus":baseline.focus,"pivot_px":baseline.pivot?.array as Any? ?? NSNull(),
          "tip_px":baseline.tip?.array as Any? ?? NSNull()],output.appendingPathComponent("baseline.json"))
var rows:[[String:Any]]=[]
for frame in request.frames {
    let current=image(frame.path)
    guard current.width==reference.width,current.height==reference.height else { fail("Source dimensions changed") }
    var result=track(current,reference,baseline,s)
    if !baseline.reasons.isEmpty { result.horn.reasons.append("reference_horn_not_resolved");result.horn.pivot=nil;result.horn.tip=nil }
    var row=json(result);row["id"]=frame.id;row["source"]="saved_live_camera_pixels"
    rows.append(row)
    overlay(current,result,request.overlay_roi,output.appendingPathComponent(frame.id+"-tracking.png"),false,request.recorded_motion_analysis ?? false)
}
try save(rows,output.appendingPathComponent("tracked-pixels.json"))
if request.digital_controls {
    var controls:[[String:Any]]=[]
    var kinds=["occluded_horn","partial_horn_occlusion","blurred_horn","body_shift","body_patch_occlusion"]
    if s.camera_registration != nil { kinds += ["camera_shift_exceeds_bound","background_patch_occlusion","background_patch_disagreement"] }
    for kind in kinds {
        let current=modified(reference,s,baseline,kind,request.overlay_roi)
        let result=track(current,reference,baseline,s)
        var row=json(result);row["control"]=kind;row["source"]="digitally_modified_saved_frame";row["physical_fault_injection"]=false
        controls.append(row)
        overlay(current,result,request.overlay_roi,output.appendingPathComponent("control-"+kind+".png"),true)
    }
    try save(controls,output.appendingPathComponent("digital-controls.json"))
}
print("{\"status\":\"pixel_processing_completed\",\"calibrated_angle_verification\":false}")
