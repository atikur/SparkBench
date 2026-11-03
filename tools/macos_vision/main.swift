// Local image measurements only. No hardware access, expected labels or network.
import Foundation
import CoreGraphics
import CoreImage
import ImageIO

struct Circle: Decodable { let center_x: Int; let center_y: Int; let radius: Int }
struct Geometry: Decodable {
    let image_width: Int; let image_height: Int
    let leds: [String: Circle]
    let oled_corners: [[Double]]
    let rectified_width: Int; let rectified_height: Int
    let label_crop: [Double]
    let reference_frame: String
    let maximum_registration_shift_pixels: Double
    let minimum_registration_scale: Double
    let maximum_registration_scale: Double
    let registration_translation_pixels: Double
    let maximum_registration_error: Double
}
struct Frame: Decodable { let id: String; let path: String }
struct Request: Decodable { let geometry: Geometry; let frames: [Frame] }

func failure(_ text: String) -> NSError {
    NSError(domain: "SparkBenchVision", code: 1,
            userInfo: [NSLocalizedDescriptionKey: text])
}
func emit(_ object: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    print(String(decoding: data, as: UTF8.self))
    fflush(stdout)
}
func luminance(_ pixels: [UInt8], _ width: Int, _ x: Int, _ y: Int) -> Double {
    let i = (y * width + x) * 4
    return 0.2126 * Double(pixels[i]) + 0.7152 * Double(pixels[i+1])
           + 0.0722 * Double(pixels[i+2])
}

struct Transform { let scale: Double; let dx: Double; let dy: Double; let error: Double }
func register(_ pixels: [UInt8], _ reference: [UInt8], _ geometry: Geometry,
              _ width: Int, _ height: Int) throws -> Transform {
    var samples: [(Double,Double,Double)] = []
    for edge in 0..<4 {
        let a=geometry.oled_corners[edge], b=geometry.oled_corners[(edge+1)%4]
        let length=hypot(b[0]-a[0],b[1]-a[1])
        guard length > 20 else { throw failure("Degenerate OLED edge") }
        let nx = -(b[1]-a[1])/length, ny=(b[0]-a[0])/length
        for i in 1...25 {
            let t=Double(i)/26
            for normal in [-6.0,0.0,6.0] {
                let x=a[0]*(1-t)+b[0]*t+nx*normal
                let y=a[1]*(1-t)+b[1]*t+ny*normal
                let ix=Int(x.rounded()), iy=Int(y.rounded())
                guard ix>=0,iy>=0,ix<width,iy<height else { throw failure("Reference edge outside image") }
                samples.append((x,y,luminance(reference,width,ix,iy)))
            }
        }
    }
    func error(_ scale:Double,_ dx:Double,_ dy:Double)->Double {
        var sum=0.0
        for (x,y,referenceValue) in samples {
            let nx=Int((scale*(x-Double(width)/2)+Double(width)/2+dx).rounded())
            let ny=Int((scale*(y-Double(height)/2)+Double(height)/2+dy).rounded())
            if nx<0 || ny<0 || nx>=width || ny>=height { return .infinity }
            sum += abs(luminance(pixels,width,nx,ny)-referenceValue)
        }
        return sum/Double(samples.count)
    }
    var best=Transform(scale:1,dx:0,dy:0,error:error(1,0,0))
    let bound=geometry.registration_translation_pixels
    for scale in stride(from:geometry.minimum_registration_scale,through:geometry.maximum_registration_scale,by:0.002) {
        for dx in stride(from:-bound,through:bound,by:2.0) {
            for dy in stride(from:-bound,through:bound,by:2.0) {
                let score=error(scale,dx,dy)
                if score < best.error { best=Transform(scale:scale,dx:dx,dy:dy,error:score) }
            }
        }
    }
    let coarse=best
    for scale in stride(from:max(geometry.minimum_registration_scale,coarse.scale-0.003),
                        through:min(geometry.maximum_registration_scale,coarse.scale+0.003),by:0.0005) {
        for dx in stride(from:max(-bound,coarse.dx-2),through:min(bound,coarse.dx+2),by:0.5) {
            for dy in stride(from:max(-bound,coarse.dy-2),through:min(bound,coarse.dy+2),by:0.5) {
                let score=error(scale,dx,dy)
                if score < best.error { best=Transform(scale:scale,dx:dx,dy:dy,error:score) }
            }
        }
    }
    guard best.error <= geometry.maximum_registration_error else {
        throw failure("Static border pixels do not match reference")
    }
    return best
}

func measure(_ frame: Frame, _ geometry: Geometry, _ directory: URL,
             _ context: CIContext, _ reference: [UInt8]) throws -> [String: Any] {
    guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: frame.path) as CFURL, nil),
          let cg = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw failure("Cannot decode source JPEG")
    }
    let width = cg.width, height = cg.height
    guard width == geometry.image_width, height == geometry.image_height else {
        throw failure("Image dimensions differ from frozen geometry")
    }
    let color = CGColorSpace(name: CGColorSpace.sRGB)!
    var pixels = [UInt8](repeating: 0, count: width * height * 4)
    try pixels.withUnsafeMutableBytes { bytes in
        guard let bitmap = CGContext(data: bytes.baseAddress, width: width, height: height,
            bitsPerComponent: 8, bytesPerRow: width * 4, space: color,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else {
            throw failure("Cannot create RGB bitmap")
        }
        bitmap.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
    }
    // Align static OLED border pixels to the reference. No text recognition,
    // expected label, LED state or learned vision service participates.
    let transform = try register(pixels, reference, geometry, width, height)
    func map(_ x: Double, _ y: Double) throws -> [Double] {
        let result = [transform.scale*(x-Double(width)/2)+Double(width)/2+transform.dx,
                      transform.scale*(y-Double(height)/2)+Double(height)/2+transform.dy]
        guard hypot(result[0]-x,result[1]-y) <= geometry.maximum_registration_shift_pixels else {
            throw failure("Image shift exceeds calibration range")
        }
        return result
    }
    let corners = try geometry.oled_corners.map { try map($0[0], $0[1]) }
    var metrics: [String: Any] = [:]
    for name in ["red", "green"] {
        guard let original = geometry.leds[name] else { throw failure("LED circle missing") }
        let center = try map(Double(original.center_x), Double(original.center_y))
        let neighbor = try map(Double(original.center_x+original.radius), Double(original.center_y))
        let scale = hypot(neighbor[0]-center[0], neighbor[1]-center[1])/Double(original.radius)
        guard scale >= geometry.minimum_registration_scale, scale <= geometry.maximum_registration_scale else {
            throw failure("Image scale exceeds registered calibration range")
        }
        let circle = Circle(center_x: Int(center[0].rounded()), center_y: Int(center[1].rounded()),
                            radius: Int((Double(original.radius)*scale).rounded()))
        guard circle.radius >= 3,
              circle.center_x - circle.radius >= 0, circle.center_x + circle.radius < width,
              circle.center_y - circle.radius >= 0, circle.center_y + circle.radius < height else {
            throw failure("LED circle missing or outside image")
        }
        var sum = 0.0, rgb = [0.0, 0.0, 0.0], count = 0
        for y in (circle.center_y-circle.radius)...(circle.center_y+circle.radius) {
            for x in (circle.center_x-circle.radius)...(circle.center_x+circle.radius) {
                let dx = x-circle.center_x, dy = y-circle.center_y
                if dx*dx+dy*dy > circle.radius*circle.radius { continue }
                sum += luminance(pixels, width, x, y)
                let offset = (y*width+x)*4
                for c in 0..<3 { rgb[c] += Double(pixels[offset+c]) }
                count += 1
            }
        }
        metrics[name] = ["mean_luma_srgb": sum / Double(count),
                         "mean_rgb": rgb.map { $0 / Double(count) }, "pixels": count,
                         "center": [circle.center_x, circle.center_y], "radius": circle.radius]
    }
    guard corners.count == 4,
          corners.allSatisfy({ $0.count == 2 && $0[0] > 5 && $0[0] < Double(width-5)
                                             && $0[1] > 5 && $0[1] < Double(height-5) }) else {
        throw failure("OLED corners missing or outside image")
    }
    var supports: [Double] = []
    for edge in 0..<4 {
        let a = corners[edge], b = corners[(edge+1)%4]
        var hits = 0
        for sample in 1...25 {
            let t = Double(sample)/26
            let x = Int((a[0]*(1-t)+b[0]*t).rounded())
            let y = Int((a[1]*(1-t)+b[1]*t).rounded())
            var brightest = 0.0
            for dy in -4...4 { for dx in -4...4 {
                brightest = max(brightest, luminance(pixels, width, x+dx, y+dy))
            }}
            if brightest >= 150 { hits += 1 }
        }
        supports.append(Double(hits)/25)
    }
    let image = CIImage(cgImage: cg)
    guard let correction = CIFilter(name: "CIPerspectiveCorrection") else {
        throw failure("Perspective filter unavailable")
    }
    correction.setValue(image, forKey: kCIInputImageKey)
    let keys = ["inputTopLeft", "inputTopRight", "inputBottomRight", "inputBottomLeft"]
    for (key, point) in zip(keys, corners) {
        correction.setValue(CIVector(x: point[0], y: Double(height)-point[1]), forKey: key)
    }
    guard let corrected = correction.outputImage else { throw failure("Cannot rectify OLED") }
    let zero = corrected.transformed(by: CGAffineTransform(translationX: -corrected.extent.minX,
                                                           y: -corrected.extent.minY))
    let sized = zero.transformed(by: CGAffineTransform(scaleX: Double(geometry.rectified_width)/zero.extent.width,
                                                       y: Double(geometry.rectified_height)/zero.extent.height))
    let crop = geometry.label_crop
    guard crop.count == 4, crop[0] >= 0, crop[1] >= 0, crop[2] > 0, crop[3] > 0,
          crop[0]+crop[2] <= Double(geometry.rectified_width),
          crop[1]+crop[3] <= Double(geometry.rectified_height) else { throw failure("Invalid label crop") }
    let bottom = Double(geometry.rectified_height)-crop[1]-crop[3]
    let label = sized.cropped(to: CGRect(x: crop[0], y: bottom, width: crop[2], height: crop[3]))
        .transformed(by: CGAffineTransform(translationX: -crop[0], y: -bottom))
    let fullName = frame.id + "-oled.png", labelName = frame.id + "-label.png"
    try context.writePNGRepresentation(of: sized, to: directory.appendingPathComponent(fullName),
                                      format: .RGBA8, colorSpace: color)
    try context.writePNGRepresentation(of: label, to: directory.appendingPathComponent(labelName),
                                      format: .RGBA8, colorSpace: color)
    return ["id": frame.id, "status": "measured", "width": width, "height": height,
            "leds": metrics, "oled_border_support": supports,
            "oled_crop": fullName, "label_crop": labelName,
            "registered_corners": corners,
            "registration": ["scale": transform.scale, "dx": transform.dx, "dy": transform.dy,
                             "mean_absolute_luma_error": transform.error]]
}

do {
    guard CommandLine.arguments.count == 3 else { throw failure("Expected REQUEST_JSON NEW_OUTPUT_DIRECTORY") }
    let request = try JSONDecoder().decode(Request.self,
        from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
    guard request.geometry.oled_corners.count == 4,
          request.geometry.oled_corners.allSatisfy({ $0.count == 2 }),
          let referenceSource = CGImageSourceCreateWithURL(URL(fileURLWithPath: request.geometry.reference_frame) as CFURL, nil),
          let reference = CGImageSourceCreateImageAtIndex(referenceSource, 0, nil),
          reference.width == request.geometry.image_width, reference.height == request.geometry.image_height else {
        throw failure("Valid reference image and four OLED corners required")
    }
    let color = CGColorSpace(name: CGColorSpace.sRGB)!
    var referencePixels = [UInt8](repeating: 0, count: reference.width*reference.height*4)
    try referencePixels.withUnsafeMutableBytes { bytes in
        guard let bitmap = CGContext(data: bytes.baseAddress, width: reference.width, height: reference.height,
            bitsPerComponent: 8, bytesPerRow: reference.width*4, space: color,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else {
            throw failure("Cannot render reference pixels")
        }
        bitmap.draw(reference, in: CGRect(x:0,y:0,width:reference.width,height:reference.height))
    }
    let directory = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
    guard !FileManager.default.fileExists(atPath: directory.path) else { throw failure("Output already exists") }
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let context = CIContext()
    for frame in request.frames {
        guard frame.id.range(of: "^[A-Za-z0-9_-]+$", options: .regularExpression) != nil else {
            throw failure("Invalid frame identifier")
        }
        let row: [String: Any] = autoreleasepool {
            do { return try measure(frame, request.geometry, directory, context, referencePixels) }
            catch { return ["id": frame.id, "status": "unknown", "error": error.localizedDescription] }
        }
        try emit(row)
    }
} catch {
    fputs("Local image reader failed: \(error.localizedDescription)\n", stderr)
    exit(2)
}
