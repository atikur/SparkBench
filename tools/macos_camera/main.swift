// Local, video-only acquisition. Never sends serial commands or infers a pass.
import AVFoundation
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers

func emit(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
       let line = String(data: data, encoding: .utf8) { print(line) }
}

func fail(_ message: String) -> Never {
    emit(["status": "error", "error": message])
    exit(2)
}

func permissionName() -> String {
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized: return "authorized"
    case .denied: return "denied"
    case .restricted: return "restricted"
    case .notDetermined: return "not_determined"
    @unknown default: return "unknown"
    }
}

// Read-only diagnostics. Enabled is a user preference; active is device-specific.
// Record samples as well as discovery because effects may activate after startup.
func cameraEffects(_ device: AVCaptureDevice) -> [String: Any] {
    var result: [String: Any] = [:]
    if #available(macOS 12.3, *) {
        result["center_stage_enabled"] = AVCaptureDevice.isCenterStageEnabled
        result["center_stage_active"] = device.isCenterStageActive
        result["center_stage_supported"] = device.activeFormat.isCenterStageSupported
        result["center_stage_control_mode"] = AVCaptureDevice.centerStageControlMode.rawValue
    }
    if #available(macOS 12.0, *) {
        result["portrait_enabled"] = AVCaptureDevice.isPortraitEffectEnabled
        result["portrait_active"] = device.isPortraitEffectActive
    }
    return result
}

func cameraInfo(_ device: AVCaptureDevice) -> [String: Any] {
    return ["id": device.uniqueID, "name": device.localizedName,
            "type": device.deviceType.rawValue, "connected": device.isConnected,
            "effects_snapshot": cameraEffects(device)]
}

func devices() -> [AVCaptureDevice] {
    var types: [AVCaptureDevice.DeviceType] = [.builtInWideAngleCamera]
    if #available(macOS 14.0, *) {
        types += [.external, .continuityCamera]
    } else {
        types += [.externalUnknown]
    }
    let discovery = AVCaptureDevice.DiscoverySession(deviceTypes: types, mediaType: .video,
                                                     position: .unspecified)
    // Continuity devices can arrive asynchronously after discovery begins.
    // Retain the discovery session and service its run loop before the snapshot.
    RunLoop.current.run(until: Date().addingTimeInterval(2))
    return discovery.devices
}

func requirePermission() {
    if AVCaptureDevice.authorizationStatus(for: .video) == .notDetermined {
        // Run the main run loop while the user answers the native permission prompt.
        AVCaptureDevice.requestAccess(for: .video) { _ in }
        let deadline = Date().addingTimeInterval(60)
        while permissionName() == "not_determined" && Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        }
    }
    guard permissionName() == "authorized" else {
        fail("Camera access is \(permissionName()). Allow the launching app under System Settings > Privacy & Security > Camera, then retry.")
    }
}

final class FrameWriter: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let device: AVCaptureDevice
    let directory: URL
    let interval: Double
    let journal: FileHandle
    let context = CIContext()
    var lastSaved = -Double.infinity
    var count = 0
    var errors: [String] = []

    init(directory: URL, fps: Double, device: AVCaptureDevice) throws {
        self.device = device
        self.directory = directory
        self.interval = 1.0 / fps
        let path = directory.appendingPathComponent("frames.jsonl")
        guard FileManager.default.createFile(atPath: path.path, contents: nil) else {
            throw NSError(domain: "SparkBench", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Cannot create frame journal"])
        }
        journal = try FileHandle(forWritingTo: path)
        super.init()
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sample: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        autoreleasepool {
            guard errors.isEmpty else { return }
            let uptime = ProcessInfo.processInfo.systemUptime
            guard uptime - lastSaved >= interval else { return }
            guard let buffer = CMSampleBufferGetImageBuffer(sample),
                  let image = context.createCGImage(CIImage(cvPixelBuffer: buffer),
                      from: CGRect(x: 0, y: 0, width: CVPixelBufferGetWidth(buffer),
                                   height: CVPixelBufferGetHeight(buffer))) else {
                errors.append("Could not convert video frame")
                return
            }
            let name = String(format: "frame-%06d.jpg", count + 1)
            let url = directory.appendingPathComponent(name)
            guard let destination = CGImageDestinationCreateWithURL(
                url as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else {
                errors.append("Cannot create \(name)")
                return
            }
            CGImageDestinationAddImage(destination, image,
                [kCGImageDestinationLossyCompressionQuality: 0.95] as CFDictionary)
            guard CGImageDestinationFinalize(destination) else {
                errors.append("Cannot write \(name)")
                return
            }
            let row: [String: Any] = [
                "frame": count + 1, "file": name,
                "sample_pts_seconds": CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample)),
                "host_uptime_seconds": uptime,
                "host_unix_seconds": Date().timeIntervalSince1970,
                "width": image.width, "height": image.height,
                "camera_effects": cameraEffects(device)
            ]
            do {
                var data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
                data.append(0x0A)
                try journal.write(contentsOf: data)
                count += 1
                lastSaved = uptime
            } catch {
                errors.append("Cannot append frame journal: \(error.localizedDescription)")
            }
        }
    }
}

let args = Array(CommandLine.arguments.dropFirst())
guard let action = args.first else { fail("Expected list or capture") }
if action == "authorize" {
    requirePermission()
    emit(["schema_version": 1, "camera_permission": permissionName(),
          "scope": "Camera permission only; no recording"])
    exit(0)
}
if action == "list" {
    emit(["schema_version": 1, "backend": "avfoundation",
          "camera_permission": permissionName(), "devices": devices().map(cameraInfo),
          "continuity_camera_opt_in": Bundle.main.object(forInfoDictionaryKey:
              "NSCameraUseContinuityCameraDeviceType") as? Bool ?? false])
    exit(0)
}
guard action == "capture", args.count == 5,
      let seconds = Double(args[3]), seconds.isFinite, seconds >= 1, seconds <= 60,
      let fps = Double(args[4]), fps.isFinite, fps >= 1, fps <= 10 else {
    fail("Expected capture DEVICE_ID OUTPUT_DIRECTORY SECONDS[1..60] SAMPLE_FPS[1..10]")
}
requirePermission()
guard let device = devices().first(where: { $0.uniqueID == args[1] }) else {
    fail("Selected camera is not available. Run camera list again; no other camera was substituted.")
}
let directory = URL(fileURLWithPath: args[2], isDirectory: true)
guard !FileManager.default.fileExists(atPath: directory.path) else {
    fail("Output directory already exists; use a new path to preserve previous evidence.")
}

do {
    let session = AVCaptureSession()
    session.beginConfiguration()
    let input = try AVCaptureDeviceInput(device: device)
    guard session.canAddInput(input) else { fail("Cannot attach selected camera input") }
    session.addInput(input)
    if session.canSetSessionPreset(.hd1920x1080) { session.sessionPreset = .hd1920x1080 }
    let output = AVCaptureVideoDataOutput()
    output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
    output.alwaysDiscardsLateVideoFrames = true
    guard session.canAddOutput(output) else { fail("Cannot attach video output") }
    session.addOutput(output)
    if let connection = output.connection(with: .video), connection.isVideoMirroringSupported {
        connection.automaticallyAdjustsVideoMirroring = false
        connection.isVideoMirrored = false
    }
    session.commitConfiguration()
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let writer = try FrameWriter(directory: directory, fps: fps, device: device)
    let queue = DispatchQueue(label: "org.sparkbench.camera.frames")
    output.setSampleBufferDelegate(writer, queue: queue)
    let start = Date()
    let journalURL = directory.appendingPathComponent("capture.json")
    var report: [String: Any] = [
        "schema_version": 1, "status": "recording", "source": "live_camera",
        "backend": "avfoundation", "camera": cameraInfo(device),
        "started_at_utc": ISO8601DateFormatter().string(from: start),
        "requested_duration_seconds": seconds, "requested_sample_fps": fps,
        "frames_index": "frames.jsonl", "audio_recorded": false,
        "scope": "Raw camera frames only; no physical pass/fail, serial synchronization, or model inference."
    ]
    try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
        .write(to: journalURL, options: .atomic)
    session.startRunning()
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
    session.stopRunning()
    output.setSampleBufferDelegate(nil, queue: nil)
    queue.sync {}
    try writer.journal.close()
    report["status"] = writer.count > 0 && writer.errors.isEmpty ? "captured" : "incomplete"
    report["frame_count"] = writer.count
    report["errors"] = writer.errors
    report["ended_at_utc"] = ISO8601DateFormatter().string(from: Date())
    report["output_directory"] = directory.path
    try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
        .write(to: journalURL, options: .atomic)
    emit(report)
    exit(writer.count > 0 && writer.errors.isEmpty ? 0 : 2)
} catch {
    fail(error.localizedDescription)
}
