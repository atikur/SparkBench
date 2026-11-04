import CoreGraphics
import Foundation
import ImageIO
import Vision
import simd

struct Input: Decodable {
    let reference: String
    let current: String
    let landmarks: [[Int]] // OLED corners followed by the two lens centers.
    let radii: [Int]
    let screen: [Int]?
}
struct RegistrationError: Error {}

struct Component {
    let pixels: [Int]
    let minX: Int, minY: Int, maxX: Int, maxY: Int
    var width: Int { maxX - minX + 1 }
    var height: Int { maxY - minY + 1 }
}

func components(_ mask: [Bool], width: Int, height: Int) -> [Component] {
    var remaining = mask
    var result: [Component] = []
    for start in remaining.indices where remaining[start] {
        var pixels = [start], cursor = 0
        remaining[start] = false
        var minX = width, minY = height, maxX = 0, maxY = 0
        while cursor < pixels.count {
            let index = pixels[cursor], x = index % width, y = index / width
            cursor += 1
            minX = min(minX, x); minY = min(minY, y)
            maxX = max(maxX, x); maxY = max(maxY, y)
            for dy in max(-1, -y)...min(1, height - 1 - y) {
                for dx in max(-1, -x)...min(1, width - 1 - x) {
                    let neighbor = index + dy * width + dx
                    if remaining[neighbor] {
                        remaining[neighbor] = false
                        pixels.append(neighbor)
                    }
                }
            }
        }
        if pixels.count >= 20 {
            result.append(Component(pixels: pixels, minX: minX, minY: minY, maxX: maxX, maxY: maxY))
        }
    }
    return result
}

func locate(_ input: Input, screen: [Int]) throws -> [String: Any] {
    let current = try image(input.current)
    let w = current.width, h = current.height
    guard w <= 1920, h <= 1920, screen.count == 4,
          screen[0] >= 0, screen[1] >= 0, screen[2] < w, screen[3] < h,
          screen[0] < screen[2], screen[1] < screen[3],
          input.radii.count == 2, input.radii.allSatisfy({ (3...60).contains($0) })
    else { throw RegistrationError() }
    var rgb = [UInt8](repeating: 0, count: w * h * 4)
    try rgb.withUnsafeMutableBytes { data in
        guard let context = CGContext(data: data.baseAddress, width: w, height: h,
            bitsPerComponent: 8, bytesPerRow: w * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)
        else { throw RegistrationError() }
        context.draw(current, in: CGRect(x: 0, y: 0, width: w, height: h))
    }
    let sw = screen[2] - screen[0] + 1, sh = screen[3] - screen[1] + 1
    let bright = (0..<(sw * sh)).map { index -> Bool in
        let pixel = ((screen[1] + index / sw) * w + screen[0] + index % sw) * 4
        return min(rgb[pixel], rgb[pixel+1], rgb[pixel+2]) >= 150
    }
    let outlines = components(bright, width: sw, height: sh).filter {
        $0.width >= sw * 3 / 4 && $0.height >= sh * 3 / 4
    }
    guard outlines.count == 1 else { throw RegistrationError() }
    let perimeter = outlines[0].pixels
    let corners = [
        perimeter.min { $0 % sw + $0 / sw < $1 % sw + $1 / sw }!,
        perimeter.max { $0 % sw - $0 / sw < $1 % sw - $1 / sw }!,
        perimeter.max { $0 % sw + $0 / sw < $1 % sw + $1 / sw }!,
        perimeter.min { $0 % sw - $0 / sw < $1 % sw - $1 / sw }!,
    ].map { [screen[0] + $0 % sw, screen[1] + $0 / sw] }

    let lenses = try input.radii.enumerated().map { channel, radius -> [Int] in
        let mask = (0..<(w * h)).map { index -> Bool in
            let r = Int(rgb[index*4]), g = Int(rgb[index*4+1]), b = Int(rgb[index*4+2])
            // Off lenses reflect their pigment. Exclude bright, emissive reds.
            return channel == 0 ? r - max(g,b) >= 42 && r < 230 : g-r >= 15 && g-b >= 23
        }
        let candidates = components(mask, width: w, height: h).filter { region in
            guard min(region.width, region.height) >= radius * 2 + 1,
                  max(region.width, region.height) <= radius * 7,
                  max(region.width, region.height) * 2 <= min(region.width, region.height) * 3,
                  region.pixels.count * 5 >= region.width * region.height * 3 else { return false }
            let x = (region.minX + region.maxX) / 2, y = (region.minY + region.maxY) / 2
            return (-radius...radius).allSatisfy { dy in
                (-radius...radius).allSatisfy { dx in
                    dx*dx + dy*dy > radius*radius || mask[(y+dy)*w+x+dx]
                }
            }
        }
        guard candidates.count == 1 else { throw RegistrationError() }
        let lens = candidates[0]
        return [(lens.minX + lens.maxX) / 2, (lens.minY + lens.maxY) / 2]
    }
    return ["landmarks": corners + lenses]
}

func image(_ path: String) throws -> CGImage {
    guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { throw RegistrationError() }
    return image
}

func gray(_ image: CGImage) throws -> [UInt8] {
    var bytes = [UInt8](repeating: 0, count: image.width * image.height)
    try bytes.withUnsafeMutableBytes { data in
        guard let context = CGContext(data: data.baseAddress, width: image.width,
            height: image.height, bitsPerComponent: 8, bytesPerRow: image.width,
            space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue)
        else { throw RegistrationError() }
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
    }
    return bytes
}

func register(_ input: Input) throws -> [String: Any] {
    let prior = try image(input.reference), next = try image(input.current)
    let w = prior.width, h = prior.height
    guard w == next.width, h == next.height, w <= 1920, h <= 1920,
          input.landmarks.count == 6, input.landmarks.allSatisfy({ $0.count == 2 }),
          input.radii.count == 2, input.radii.allSatisfy({ (3...60).contains($0) })
    else { throw RegistrationError() }

    let request = VNHomographicImageRegistrationRequest(targetedCGImage: next)
    try VNImageRequestHandler(cgImage: prior).perform([request])
    guard let result = request.results?.first else { throw RegistrationError() }
    let warp = simd_inverse(result.warpTransform)

    func project(_ x: Int, _ y: Int) throws -> [Int] {
        // Vision uses a lower-left origin. The geometry and bitmap rows use top-left.
        let p = warp * SIMD3<Float>(Float(x), Float(h - 1 - y), 1)
        let px = p.x / p.z, py = Float(h - 1) - p.y / p.z
        guard px.isFinite, py.isFinite, px >= 0, py >= 0,
              px < Float(w - 1), py < Float(h - 1) else { throw RegistrationError() }
        return [Int(px.rounded()), Int(py.rounded())]
    }

    let projected = try input.landmarks.map { try project($0[0], $0[1]) }
    let a = try gray(prior), b = try gray(next)
    var scores: [Double] = []
    // Cross-check the local appearance of each lens; a good global warp alone
    // can be driven by the background while the breadboard or an LED moved.
    for (point, radius) in zip(input.landmarks.suffix(2), input.radii) {
        var n = 0.0, sx = 0.0, sy = 0.0, sxx = 0.0, syy = 0.0, sxy = 0.0
        for dy in stride(from: -radius * 2, through: radius * 2, by: 2) {
            for dx in stride(from: -radius * 2, through: radius * 2, by: 2) {
                let x = point[0] + dx, y = point[1] + dy
                guard x >= 0, y >= 0, x < w, y < h else { throw RegistrationError() }
                let q = try project(x, y)
                let u = Double(a[y * w + x]), v = Double(b[q[1] * w + q[0]])
                n += 1; sx += u; sy += v; sxx += u*u; syy += v*v; sxy += u*v
            }
        }
        let vx = sxx - sx*sx/n, vy = syy - sy*sy/n
        guard vx >= 36*n, vy >= 36*n else { throw RegistrationError() }
        scores.append((sxy - sx*sy/n) / sqrt(vx*vy))
    }
    return ["landmarks": projected, "lens_similarity": scores]
}

do {
    let input = try JSONDecoder().decode(Input.self, from: FileHandle.standardInput.readDataToEndOfFile())
    let result: [String: Any]
    if let screen = input.screen { result = try locate(input, screen: screen) }
    else { result = try register(input) }
    FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: result))
} catch {
    fputs("Could not align the calibrated bench and both LED neighborhoods.\n", stderr)
    exit(1)
}
