// Passive pixel diagnostics and annotated geometry. No camera/serial/model APIs.
import Foundation
import CoreGraphics
import CoreImage
import ImageIO
import UniformTypeIdentifiers
import CoreText

struct Landmark: Decodable { let name: String; let point: [Double] }
struct Frame: Decodable { let id: String; let path: String }
struct Plane: Decodable { let corners_px: [[Double]]; let plane_size: [Double] }
struct Request: Decodable {
    let reference_frame: String; let roi: [Int]; let landmarks: [Landmark]
    let shaft_center: [Double]; let horn_tip: [Double]; let axis: [[Double]]
    let frames: [Frame]; let plane_reference: Plane?
    let preview_warning: String?
}
func fail(_ message: String) -> Never { fputs(message+"\n",stderr); exit(2) }
func decode(_ path: String) -> CGImage {
    guard let source=CGImageSourceCreateWithURL(URL(fileURLWithPath:path) as CFURL,nil),
          let image=CGImageSourceCreateImageAtIndex(source,0,nil) else { fail("Cannot decode source") }
    return image
}
func write(_ image: CGImage, _ path: URL) {
    guard !FileManager.default.fileExists(atPath:path.path),
          let destination=CGImageDestinationCreateWithURL(path as CFURL,UTType.png.identifier as CFString,1,nil) else { fail("Output exists or cannot be created") }
    CGImageDestinationAddImage(destination,image,nil)
    guard CGImageDestinationFinalize(destination) else { fail("Cannot save image") }
}
func pixels(_ image: CGImage) -> [UInt8] {
    var result=[UInt8](repeating:0,count:image.width*image.height*4)
    result.withUnsafeMutableBytes { buffer in
        guard let context=CGContext(data:buffer.baseAddress,width:image.width,height:image.height,bitsPerComponent:8,bytesPerRow:image.width*4,
            space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { fail("Cannot decode pixels") }
        context.draw(image,in:CGRect(x:0,y:0,width:image.width,height:image.height))
    }
    return result
}
func luma(_ bytes: [UInt8], _ width: Int, _ x: Int, _ y: Int) -> Double {
    let i=(y*width+x)*4
    return 0.2126*Double(bytes[i]) + 0.7152*Double(bytes[i+1]) + 0.0722*Double(bytes[i+2])
}

func warning(_ context:CGContext,_ width:Int,_ height:Int,_ message:String) {
    let size=min(16.0,max(8.0,Double(width-10)/Double(max(message.count,1))/0.65))
    context.setFillColor(CGColor(gray:0.02,alpha:0.94))
    context.fill(CGRect(x:0,y:Double(height)-size*2-15,width:Double(width),height:size*2+15))
    for (index,text) in [message,"No calibrated servo angle"].enumerated() {
        let fontSize=index==0 ? size : size*0.8
        let attributes:[NSAttributedString.Key:Any]=[
            NSAttributedString.Key(kCTFontAttributeName as String):CTFontCreateWithName("Menlo-Bold" as CFString,fontSize,nil),
            NSAttributedString.Key(kCTForegroundColorAttributeName as String):CGColor(gray:1,alpha:1)]
        let line=CTLineCreateWithAttributedString(NSAttributedString(string:text,attributes:attributes))
        context.textPosition=CGPoint(x:5,y:Double(height)-5-size-Double(index)*(size+3));CTLineDraw(line,context)
    }
}

guard CommandLine.arguments.count==3 else { fail("Expected REQUEST_JSON NEW_OUTPUT_DIRECTORY") }
let request=try JSONDecoder().decode(Request.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
let output=URL(fileURLWithPath:CommandLine.arguments[2],isDirectory:true)
guard !FileManager.default.fileExists(atPath:output.path) else { fail("Existing evidence directory rejected") }
try FileManager.default.createDirectory(at:output,withIntermediateDirectories:true)
let image=decode(request.reference_frame), width=image.width, height=image.height
guard request.roi.count==4 else { fail("ROI must be x/y/width/height") }
let roi=request.roi
guard roi[0]>=0,roi[1]>=0,roi[2]>0,roi[3]>0,roi[0]+roi[2]<=width,roi[1]+roi[3]<=height,
      request.axis.count==2,request.axis.allSatisfy({$0.count==2}),request.shaft_center.count==2,request.horn_tip.count==2,
      request.landmarks.allSatisfy({$0.point.count==2}) else { fail("Invalid geometry") }
let rect=CGRect(x:roi[0],y:roi[1],width:roi[2],height:roi[3])
guard let crop=image.cropping(to:rect) else { fail("Cannot crop body ROI") }
write(crop,output.appendingPathComponent("body-crop.png"))
guard let canvas=CGContext(data:nil,width:crop.width,height:crop.height,bitsPerComponent:8,bytesPerRow:crop.width*4,
    space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue) else { fail("Cannot annotate reference") }
canvas.draw(crop,in:CGRect(x:0,y:0,width:crop.width,height:crop.height))
func local(_ p:[Double])->CGPoint { CGPoint(x:p[0]-Double(roi[0]),y:Double(roi[3])-(p[1]-Double(roi[1]))) }
func line(_ a:[Double],_ b:[Double],_ color:CGColor) {
    canvas.setStrokeColor(color);canvas.setLineWidth(1.5)
    canvas.move(to:local(a));canvas.addLine(to:local(b));canvas.strokePath()
}
func marker(_ p:[Double],_ label:String,_ color:CGColor) {
    let center=local(p)
    canvas.setStrokeColor(color);canvas.setLineWidth(1.5)
    canvas.strokeEllipse(in:CGRect(x:center.x-4,y:center.y-4,width:8,height:8))
    let attributes:[NSAttributedString.Key:Any]=[
        NSAttributedString.Key(kCTFontAttributeName as String):CTFontCreateWithName("Menlo" as CFString,11,nil),
        NSAttributedString.Key(kCTForegroundColorAttributeName as String):color]
    let text=CTLineCreateWithAttributedString(NSAttributedString(string:label,attributes:attributes))
    canvas.textPosition=CGPoint(x:center.x+6,y:center.y+4);CTLineDraw(text,canvas)
}
let cyan=CGColor(red:0,green:1,blue:1,alpha:1)
let yellow=CGColor(red:1,green:1,blue:0,alpha:1)
let magenta=CGColor(red:1,green:0,blue:1,alpha:1)
line(request.axis[0],request.axis[1],cyan)
line(request.shaft_center,request.horn_tip,yellow)
for landmark in request.landmarks { marker(landmark.point,landmark.name,cyan) }
marker(request.shaft_center,"S",magenta);marker(request.horn_tip,"T",yellow)
marker(request.axis[0],"A",cyan);marker(request.axis[1],"B",cyan)
if let message=request.preview_warning { warning(canvas,crop.width,crop.height,message) }
guard let annotated=canvas.makeImage() else { fail("Cannot create annotated reference") }
write(annotated,output.appendingPathComponent("body-reference-overlay.png"))

let reference=pixels(image)
var diagnostics:[[String:Any]]=[]
for frame in request.frames {
    let current=decode(frame.path)
    guard current.width==width,current.height==height else { fail("Frame dimensions changed") }
    let bytes=pixels(current)
    var best=(dx:0,dy:0,error:Double.infinity)
    for dy in -4...4 { for dx in -4...4 {
        var sum=0.0,count=0
        for landmark in request.landmarks {
            let x=Int(landmark.point[0].rounded()),y=Int(landmark.point[1].rounded())
            for py in -5...5 { for px in -5...5 {
                guard x+px-4>=0,y+py-4>=0,x+px+4<width,y+py+4<height else { fail("Reference patch exceeds frame") }
                sum += abs(luma(reference,width,x+px,y+py)-luma(bytes,width,x+px+dx,y+py+dy));count += 1
            }}
        }
        let error=sum/Double(count)
        if error<best.error { best=(dx,dy,error) }
    }}
    diagnostics.append(["frame":frame.id,"best_translation_pixels":[best.dx,best.dy],"mean_absolute_luma_difference":best.error,
                        "scope":"Static patch-match diagnostic only; not automatic pose or angle verification"])
}

if let plane=request.plane_reference {
    guard plane.corners_px.count==4,plane.plane_size.count==2,plane.plane_size.allSatisfy({$0>0}) else { fail("Invalid plane") }
    let source=CIImage(cgImage:image)
    guard let filter=CIFilter(name:"CIPerspectiveCorrection") else { fail("Perspective filter unavailable") }
    filter.setValue(source,forKey:kCIInputImageKey)
    for (name,p) in zip(["inputTopLeft","inputTopRight","inputBottomRight","inputBottomLeft"],plane.corners_px) {
        guard p.count==2 else { fail("Invalid plane point") }
        filter.setValue(CIVector(x:p[0],y:Double(height)-p[1]),forKey:name)
    }
    guard let corrected=filter.outputImage else { fail("Cannot rectify plane") }
    let ratio=plane.plane_size[0]/plane.plane_size[1]
    let outWidth=min(1024.0,1024*ratio),outHeight=min(1024.0,1024/ratio)
    let zero=corrected.transformed(by:CGAffineTransform(translationX:-corrected.extent.minX,y:-corrected.extent.minY))
    let sized=zero.transformed(by:CGAffineTransform(scaleX:outWidth/zero.extent.width,y:outHeight/zero.extent.height))
    if let message=request.preview_warning {
        guard let cg=CIContext().createCGImage(sized,from:sized.extent),
              let context=CGContext(data:nil,width:cg.width,height:cg.height,bitsPerComponent:8,bytesPerRow:cg.width*4,
                space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue) else { fail("Cannot render unverified plane preview") }
        context.draw(cg,in:CGRect(x:0,y:0,width:cg.width,height:cg.height))
        warning(context,cg.width,cg.height,message)
        guard let labeled=context.makeImage() else { fail("Cannot label preview") }
        write(labeled,output.appendingPathComponent("unverified-card-plane.png"))
    } else {
        try CIContext().writePNGRepresentation(of:sized,to:output.appendingPathComponent("reference-plane-rectified.png"),format:.RGBA8,colorSpace:CGColorSpace(name:CGColorSpace.sRGB)!)
    }
}
let data=try JSONSerialization.data(withJSONObject:["frames":diagnostics,"perspective_image_created":request.plane_reference != nil,
    "unverified_preview_only":request.preview_warning != nil,"calibrated_angle_verification":false],options:[.sortedKeys])
print(String(decoding:data,as:UTF8.self))
