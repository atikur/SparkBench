// Synthetic RGB fixtures exercising the exact production detector core.
import Foundation
func expect(_ condition:Bool,_ message:String) { if !condition { fatalError(message) } }
let settings=try JSONDecoder().decode(TrackerSettings.self,from:Data("""
{"horn_roi":[95,90,230,225],"pivot_hint":[200,200],"body_patches":[[110,350],[280,350],[110,430],[280,430]],
"search_pixels":8,"patch_radius":5,"maximum_body_shift_pixels":2,"maximum_patch_spread_pixels":2,
"maximum_patch_error":14,"minimum_patch_texture":4,"minimum_white_luma":170,"maximum_white_chroma":45,
"minimum_component_area":1800,"maximum_component_area":10000,"minimum_elongation":2,
"pivot_search_pixels":14,"minimum_pivot_contrast":6,"minimum_horn_length":50,"maximum_horn_length":150,
"minimum_focus_ratio":0.4,"minimum_focus_variance":3,"minimum_area_ratio":0.65,"maximum_area_ratio":1.35}
""".utf8))
func fixture(_ degrees:Double,_ hub:Bool=true)->TrackerImage {
    let w=512,h=512
    var bytes=[UInt8](repeating:255,count:w*h*4)
    let a=degrees*Double.pi/180,ux=cos(a),uy=sin(a)
    for y in 0..<h { for x in 0..<w {
        var value=70
        if x<80 || x>350 { value=25+(x*73+y*131+x*y*17)%130 }
        if x>=95 && x<=300 && y>=330 && y<=450 { value=25+(x*73+y*131+x*y*17)%130 }
        let dx=Double(x-200),dy=Double(y-200),along=dx*ux+dy*uy,across = -dx*uy+dy*ux
        let circle=dx*dx/(28*28)+dy*dy/(23*23)<=1
        let arm=(along>=0 && along<=80 && abs(across)<=17) || ((along-80)*(along-80)+across*across<=17*17)
        if circle || arm { value=225 }
        if hub && dx*dx+dy*dy<=5*5 { value=170 }
        for c in 0..<3 { bytes[(y*w+x)*4+c]=UInt8(value) }
    }}
    return TrackerImage(width:w,height:h,rgba:bytes)
}
let reference=fixture(100)
let baseline=observeHorn(reference,settings,TrackerPoint(x:0,y:0))
expect(baseline.reasons.isEmpty,"Reference failed: \(baseline.reasons)")
// Bounded exposure compensation must retain geometric/occlusion rejection.
let exposurePatches=[[40.0,60.0],[390,60],[390,280],[40,280]]
var exposureJSON=try JSONSerialization.jsonObject(with:JSONEncoder().encode(settings)) as! [String:Any]
exposureJSON["exposure_reference_patches"]=exposurePatches
let exposureSettings=try JSONDecoder().decode(TrackerSettings.self,from:JSONSerialization.data(withJSONObject:exposureJSON))
var exposureBytes=reference.rgba
for p in exposurePatches { for y in (Int(p[1])-6)...(Int(p[1])+6) { for x in (Int(p[0])-6)...(Int(p[0])+6) {
    for c in 0..<3 { exposureBytes[(y*512+x)*4+c]=200 }
}}}
let exposureReference=TrackerImage(width:512,height:512,rgba:exposureBytes)
func dimmed(_ bytes:[UInt8],_ gain:Double)->TrackerImage {
    var result=bytes
    for i in 0..<(512*512) { for c in 0..<3 { result[i*4+c]=UInt8((Double(bytes[i*4+c])*gain).rounded()) } }
    return TrackerImage(width:512,height:512,rgba:result)
}
let corrected=track(dimmed(exposureBytes,0.82),exposureReference,baseline,exposureSettings)
expect(corrected.accepted,"Bounded global dimming rejected: \(corrected.reasons)")
expect(hypot(corrected.horn.tip!.x-baseline.tip!.x,corrected.horn.tip!.y-baseline.tip!.y)<1,"Exposure correction changed horn geometry")
expect(!track(dimmed(exposureBytes,0.6),exposureReference,baseline,exposureSettings).accepted,"Excessive exposure change accepted")
var inconsistent=exposureBytes
for y in 54...66 { for x in 34...46 { for c in 0..<3 { inconsistent[(y*512+x)*4+c]=150 } } }
expect(!track(TrackerImage(width:512,height:512,rgba:inconsistent),exposureReference,baseline,exposureSettings).accepted,"Inconsistent exposure references accepted")
var covered=exposureBytes
for y in 90..<315 { for x in 95..<325 { for c in 0..<3 { covered[(y*512+x)*4+c]=20 } } }
expect(!track(dimmed(covered,0.82),exposureReference,baseline,exposureSettings).accepted,"Exposure correction hid horn occlusion")
var shiftedExposure=exposureBytes
for y in 330..<450 { for x in 95..<310 { for c in 0..<4 {
    shiftedExposure[(y*512+x)*4+c]=exposureBytes[(y*512+x-5)*4+c]
}}}
expect(!track(dimmed(shiftedExposure,0.82),exposureReference,baseline,exposureSettings).accepted,"Exposure correction hid body displacement")
exposureJSON["white_reference_fraction"]=0.75
let relativeWhiteSettings=try JSONDecoder().decode(TrackerSettings.self,from:JSONSerialization.data(withJSONObject:exposureJSON))
let darkReference=dimmed(exposureBytes,0.65)
let darkBaseline=observeHorn(darkReference,relativeWhiteSettings,TrackerPoint(x:0,y:0))
expect(darkBaseline.reasons.isEmpty,"Reference-relative white segmentation failed")
expect(track(darkReference,darkReference,darkBaseline,relativeWhiteSettings).accepted,"Clean dark reference rejected")
expect(!track(dimmed(covered,0.65),darkReference,darkBaseline,relativeWhiteSettings).accepted,"Relative white segmentation hid occlusion")
for fraction in [0.0,0.69,0.86,1.0] {
    exposureJSON["white_reference_fraction"]=fraction
    let bad=try JSONDecoder().decode(TrackerSettings.self,from:JSONSerialization.data(withJSONObject:exposureJSON))
    expect(!observeHorn(darkReference,bad,TrackerPoint(x:0,y:0)).reasons.isEmpty,"Invalid white reference fraction accepted")
}
for angle in [70.0,95,120,145,190] {
    let observed=track(fixture(angle),reference,baseline,settings)
    expect(observed.accepted,"Synthetic clean pose rejected at \(angle): \(observed.reasons)")
    let p=observed.horn.pivot!,t=observed.horn.tip!
    expect(hypot(p.x-200,p.y-200)<1,"Hub localization failed")
    let measured=atan2(t.y-p.y,t.x-p.x)*180/Double.pi
    let error=abs((measured-angle+540).truncatingRemainder(dividingBy:360)-180)
    expect(error<3,"Synthetic direction mismatch: \(error)")
}
let noHub=track(fixture(100,false),reference,baseline,settings)
expect(!noHub.accepted && noHub.horn.pivot==nil,"Missing hub feature must be unknown")
var shifted=reference.rgba
for y in 0..<512 { for x in 0..<512 {
    for c in 0..<4 { shifted[(y*512+x)*4+c]=x>=5 ? reference.rgba[(y*512+x-5)*4+c] : 70 }
}}
let moved=track(TrackerImage(width:512,height:512,rgba:shifted),reference,baseline,settings)
expect(!moved.accepted && moved.body.reasons.contains("body_moved"),"Moved body was accepted")
expect(moved.horn.pivot==nil && moved.horn.tip==nil,"Moved body points leaked")
var blocked=reference.rgba
for y in 90..<315 { for x in 95..<325 { for c in 0..<3 { blocked[(y*512+x)*4+c]=20 } } }
let occluded=track(TrackerImage(width:512,height:512,rgba:blocked),reference,baseline,settings)
expect(!occluded.accepted && occluded.horn.tip==nil,"Occluded horn was accepted")
// Independent background mode accepts bounded common translation, never a
// servo-only displacement. This is generated-image evidence, not physical motion.
var registrationJSON=try JSONSerialization.jsonObject(with:JSONEncoder().encode(settings)) as! [String:Any]
registrationJSON["camera_registration"]=["background_patches":[[45,55],[400,55],[400,430]],"maximum_shift_pixels":4]
let registeredSettings=try JSONDecoder().decode(TrackerSettings.self,from:JSONSerialization.data(withJSONObject:registrationJSON))
func translated(_ dx:Int,_ dy:Int,_ servoOnly:Bool=false)->TrackerImage {
    var bytes=reference.rgba
    for y in 0..<512 { for x in 0..<512 {
        if servoOnly && !(x>=90 && x<335 && y>=85 && y<460) { continue }
        for c in 0..<4 { bytes[(y*512+x)*4+c]=(x-dx>=0 && x-dx<512 && y-dy>=0 && y-dy<512) ? reference.rgba[((y-dy)*512+x-dx)*4+c] : 70 }
    }}
    return TrackerImage(width:512,height:512,rgba:bytes)
}
let cameraMoved=track(translated(2,2),reference,baseline,registeredSettings)
expect(cameraMoved.accepted,"Bounded common translation rejected: \(cameraMoved.reasons)")
expect(cameraMoved.body.cameraShift!.array==[2,2] && cameraMoved.body.residualShift!.array==[0,0],"Incorrect independent translation")
let legacyDiagonal=track(translated(2,2),reference,baseline,settings)
expect(!legacyDiagonal.accepted && legacyDiagonal.reasons.contains("body_moved"),"Legacy absolute limit changed")
let servoMoved=track(translated(5,0,true),reference,baseline,registeredSettings)
expect(!servoMoved.accepted && servoMoved.reasons.contains("body_moved_relative_to_background"),"Servo movement hidden as camera translation")
let cameraTooFar=track(translated(5,0),reference,baseline,registeredSettings)
expect(!cameraTooFar.accepted && cameraTooFar.reasons.contains("camera_displacement_exceeds_bound"),"Large camera translation accepted")
var anchorsBlocked=reference.rgba
for p in registeredSettings.camera_registration!.background_patches {
    for y in (Int(p[1])-12)...(Int(p[1])+12) { for x in (Int(p[0])-12)...(Int(p[0])+12) {
        for c in 0..<3 { anchorsBlocked[(y*512+x)*4+c]=0 }
    }}
}
let noCameraReference=track(TrackerImage(width:512,height:512,rgba:anchorsBlocked),reference,baseline,registeredSettings)
expect(!noCameraReference.accepted && noCameraReference.horn.pivot==nil,"Lost background anchors leaked pose")
let modelAnchors:[[Double]]=[[45,55],[400,55],[400,430],[45,430]]
let angle=0.2*Double.pi/180,a=0.999*cos(angle),b=0.999*sin(angle)
let known=[a,-b,1.0,b,a,-1.0]
let modelShifts=modelAnchors.map{p -> TrackerPoint in
    let q=transformed(TrackerPoint(x:p[0],y:p[1]),known)
    return TrackerPoint(x:q.x-p[0],y:q.y-p[1])
}
let fitted=similarityTransform(modelAnchors,modelShifts)!
expect(zip(known,fitted).allSatisfy{abs($0-$1)<1e-9},"Similarity fit does not recover known synthetic geometry")
registrationJSON["camera_registration"]=["background_patches":modelAnchors,"maximum_shift_pixels":4,
    "model":"similarity","maximum_rotation_degrees":0.5,"maximum_scale_change":0.005]
let similaritySettings=try JSONDecoder().decode(TrackerSettings.self,from:JSONSerialization.data(withJSONObject:registrationJSON))
expect(track(translated(2,2),reference,baseline,similaritySettings).accepted,"Similarity rejected bounded common translation")
expect(!track(translated(5,0,true),reference,baseline,similaritySettings).accepted,"Similarity hid independent body movement")
expect(!track(translated(5,0),reference,baseline,similaritySettings).accepted,"Similarity accepted excessive camera displacement")
registrationJSON["camera_registration"]=["background_patches":settings.body_patches,"maximum_shift_pixels":4]
let invalidSettings=try JSONDecoder().decode(TrackerSettings.self,from:JSONSerialization.data(withJSONObject:registrationJSON))
expect(!track(reference,reference,baseline,invalidSettings).accepted,"Body reused as independent background")
// Analytic textured pixels sampled at fractional positions exercise the actual
// matcher, independently of its cost implementation. No real angle claim.
var subpixelJSON=try JSONSerialization.jsonObject(with:JSONEncoder().encode(similaritySettings)) as! [String:Any]
subpixelJSON["patch_matching"]="bilinear_subpixel";subpixelJSON["body_patch_radius"]=9
let subpixelSettings=try JSONDecoder().decode(TrackerSettings.self,from:JSONSerialization.data(withJSONObject:subpixelJSON))
func smoothTexture(_ dx:Double,_ dy:Double)->TrackerImage {
    let w=512,h=512
    var bytes=[UInt8](repeating:255,count:w*h*4)
    for y in 0..<h { for x in 0..<w {
        let px=Double(x)-dx,py=Double(y)-dy
        let value=100+25*sin(px*0.25)+22*cos(py*0.3)+16*sin(px*0.13+py*0.2)
        for c in 0..<3 { bytes[(y*w+x)*4+c]=UInt8(value.rounded()) }
    }}
    return TrackerImage(width:w,height:h,rgba:bytes)
}
let smoothReference=smoothTexture(0,0)
for d in [TrackerPoint(x:-1.4,y:0.7),TrackerPoint(x:0.35,y:-0.6),TrackerPoint(x:2.25,y:1.5)] {
    let match=matchPatches(smoothTexture(d.x,d.y),smoothReference,subpixelSettings,settings.body_patches,radiusOverride:9)
    expect(match.reasons.isEmpty,"Fractional texture match rejected: \(match.reasons)")
    expect(match.patchShifts.allSatisfy{hypot($0.x-d.x,$0.y-d.y)<0.25},"Fractional synthetic shift inaccurate: \(match.patchShifts)")
}
let atSearchBoundary=matchPatches(smoothTexture(8,0),smoothReference,subpixelSettings,settings.body_patches,radiusOverride:9)
expect(atSearchBoundary.reasons.contains("body_search_boundary"),"Subpixel refinement hid a search-boundary match")
expect(track(translated(2,2),reference,baseline,subpixelSettings).accepted,"Subpixel common camera translation rejected")
let independentBody=track(translated(5,0,true),reference,baseline,subpixelSettings)
expect(!independentBody.accepted && independentBody.horn.pivot==nil,"Subpixel matching hid independent body movement")
let blockedBody=track(TrackerImage(width:512,height:512,rgba:blocked),reference,baseline,subpixelSettings)
expect(!blockedBody.accepted && blockedBody.horn.tip==nil,"Subpixel matching leaked an occluded horn")
var largeBackgroundJSON=subpixelJSON
var largeRegistration=largeBackgroundJSON["camera_registration"] as! [String:Any]
largeRegistration["patch_radius"]=9;largeBackgroundJSON["camera_registration"]=largeRegistration
let largeBackgroundSettings=try JSONDecoder().decode(TrackerSettings.self,from:JSONSerialization.data(withJSONObject:largeBackgroundJSON))
expect(subpixelSettings.camera_registration!.patch_radius == nil,"Legacy background radius changed")
expect(track(translated(2,2),reference,baseline,largeBackgroundSettings).accepted,"Larger background patch rejected common bounded translation")
let largeBodyShift=track(translated(5,0,true),reference,baseline,largeBackgroundSettings)
expect(!largeBodyShift.accepted && largeBodyShift.horn.pivot==nil,"Larger background patch concealed independent case movement")
expect(!track(translated(5,0),reference,baseline,largeBackgroundSettings).accepted,"Larger background patch relaxed camera displacement")
let largeOccluded=track(TrackerImage(width:512,height:512,rgba:blocked),reference,baseline,largeBackgroundSettings)
expect(!largeOccluded.accepted && largeOccluded.horn.tip==nil,"Larger background patch concealed horn occlusion")
for radius in [1,11] {
    largeRegistration["patch_radius"]=radius;largeBackgroundJSON["camera_registration"]=largeRegistration
    let bad=try JSONDecoder().decode(TrackerSettings.self,from:JSONSerialization.data(withJSONObject:largeBackgroundJSON))
    expect(!track(reference,reference,baseline,bad).accepted,"Invalid background radius accepted")
}
print("Synthetic native core: localization, bounded independent translation, legacy limits, relative body motion and obstruction checks passed; no physical evidence")
