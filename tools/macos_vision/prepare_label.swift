// Deterministic crop preparation only: no OCR, model, network or hardware I/O.
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

func fail(_ text: String) -> Never { fputs(text + "\n", stderr); exit(2) }
guard CommandLine.arguments.count == 3 else { fail("Expected INPUT_PNG NEW_OUTPUT_PNG") }
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
guard !FileManager.default.fileExists(atPath: output.path),
      let source = CGImageSourceCreateWithURL(input as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { fail("Missing image or existing output") }
let width = image.width, height = image.height
guard width > 0, height > 0, width <= 4096, height <= 4096 else { fail("Unsupported crop dimensions") }
var bytes = [UInt8](repeating: 0, count: width * height * 4)
let color = CGColorSpace(name: CGColorSpace.sRGB)!
bytes.withUnsafeMutableBytes { buffer in
    guard let context = CGContext(data: buffer.baseAddress, width: width, height: height,
        bitsPerComponent: 8, bytesPerRow: width * 4, space: color,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else {
        fail("Cannot decode RGB pixels")
    }
    context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
}
var foreground = [Bool](repeating: false, count: width * height)
for index in foreground.indices {
    let i = index * 4
    foreground[index] = 0.2126 * Double(bytes[i]) + 0.7152 * Double(bytes[i+1])
                         + 0.0722 * Double(bytes[i+2]) >= 48
}
var seen = [Bool](repeating: false, count: foreground.count)
var minX = width, minY = height, maxX = -1, maxY = -1, borderCount = 0
for start in foreground.indices where foreground[start] && !seen[start] {
    var queue = [start], cursor = 0
    seen[start] = true
    var x0 = width, y0 = height, x1 = -1, y1 = -1
    while cursor < queue.count {
        let point = queue[cursor]; cursor += 1
        let x = point % width, y = point / width
        x0 = min(x0,x); x1 = max(x1,x); y0 = min(y0,y); y1 = max(y1,y)
        for (nx,ny) in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)] {
            if nx < 0 || ny < 0 || nx >= width || ny >= height { continue }
            let index = ny * width + nx
            if foreground[index] && !seen[index] { seen[index] = true; queue.append(index) }
        }
    }
    // A full-height narrow component is the frame edge, not a label glyph.
    // All other components, including punctuation and small marks, contribute.
    if y0 == 0 && y1 == height-1 && x1-x0 < 24 { borderCount += 1; continue }
    minX = min(minX,x0); maxX = max(maxX,x1); minY = min(minY,y0); maxY = max(maxY,y1)
}
var rectangle = CGRect(x: 0, y: 0, width: width, height: height)
let blank = maxX < minX || maxY < minY
if !blank {
    let padding = 24
    let x0 = max(0,minX-padding), y0 = max(0,minY-padding)
    let x1 = min(width,maxX+padding+1), y1 = min(height,maxY+padding+1)
    rectangle = CGRect(x: x0, y: y0, width: x1-x0, height: y1-y0)
}
guard let cropped = image.cropping(to: rectangle),
      let destination = CGImageDestinationCreateWithURL(output as CFURL, UTType.png.identifier as CFString, 1, nil) else {
    fail("Cannot prepare label crop")
}
CGImageDestinationAddImage(destination, cropped, nil)
guard CGImageDestinationFinalize(destination) else { fail("Cannot save label crop") }
let report: [String: Any] = ["source_size": [width,height],
    "crop_xywh": [Int(rectangle.minX),Int(rectangle.minY),Int(rectangle.width),Int(rectangle.height)],
    "blank_foreground": blank, "full_height_border_components_ignored_for_bounds": borderCount,
    "foreground_threshold": 48, "padding_pixels": 24,
    "pixel_operation": "rectangle crop only; no glyph removal, thresholding or synthesis in output"]
let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
print(String(decoding: data, as: UTF8.self))
