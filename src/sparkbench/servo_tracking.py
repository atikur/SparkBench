"""Automatic passive pixel tracking from saved images; estimates stay unverified.

This module has no camera, serial, firmware or model/API operation. Manual ROI,
body patches and a hub search hint initialize automatic per-frame localization.
"""
import argparse
import copy
import json
import math
import platform
import shutil
import subprocess
from pathlib import Path

from .camera import ROOT
from .servo_preview import estimates, reference_notes
from .vision import digest, finite, load, save


def build_tracker():
    if platform.system()!="Darwin" or not shutil.which("xcrun"):
        raise ValueError("Native tracker requires macOS command-line tools")
    sources=[ROOT/"tools/macos_servo_tracker"/n for n in ("Tracker.swift","main.swift")]
    folder=ROOT/".cache/servo_tracker";folder.mkdir(parents=True,exist_ok=True)
    binary,stamp=folder/"PassiveServoTracker",folder/"source.sha256"
    fingerprint="".join(digest(p) for p in sources)+platform.machine()+platform.mac_ver()[0]
    if not (binary.is_file() and stamp.is_file() and stamp.read_text()==fingerprint):
        result=subprocess.run(["xcrun","swiftc","-O","-module-cache-path",str(folder/"swift-modules"),
            *map(str,sources),"-o",str(binary)],capture_output=True,text=True,timeout=180)
        if result.returncode:raise ValueError("Passive tracker build failed: "+result.stderr[-3000:])
        stamp.write_text(fingerprint)
    return binary


def joined_trace(frames, raw, preview_config, policy):
    by_id={r["id"]:r for r in raw}
    if len(by_id)!=len(raw):raise ValueError("Duplicate native frame IDs")
    expected={Path(f["file"]).stem for f in frames}
    if not set(by_id)<=expected:raise ValueError("Native tracker returned an unexpected frame")
    rows=[];last_pts=None;last_heading=None;first_heading=None
    for frame in frames:
        native=by_id.get(Path(frame["file"]).stem,{"status":"unknown","reasons":["missing_source_or_native_frame"]})
        reasons=list(native.get("reasons",[]))
        pts,host=frame.get("sample_pts_seconds"),frame.get("host_uptime_seconds")
        if not finite(pts) or not finite(host) or not 0<=host-pts<=1:
            reasons.append("unsupported_camera_timestamp_alignment")
        if finite(pts) and last_pts is not None:
            if pts<=last_pts:reasons.append("nonincreasing_camera_timestamp")
            elif pts-last_pts>policy["maximum_frame_gap_seconds"]:reasons.append("capture_gap")
        if finite(pts):last_pts=pts
        if native.get("status")!="tracked_unverified" and not reasons:reasons.append("native_tracking_unknown")
        preview=None;points=None
        if not reasons:
            pivot,tip=native.get("pivot_px"),native.get("tip_px")
            shift=native.get("quality",{}).get("body_shift_pixels")
            if (not isinstance(pivot,list) or len(pivot)!=2 or not isinstance(tip,list) or len(tip)!=2
                    or not isinstance(shift,list) or len(shift)!=2
                    or not all(finite(v) for p in (pivot,tip,shift) for v in p)):
                reasons.append("invalid_localized_points")
            else:
                config=copy.deepcopy(preview_config)
                config["body_reference"]["shaft_center_px"]=pivot
                config["body_reference"]["axis_endpoints_px"]=[[p[i]+shift[i] for i in range(2)] for p in config["body_reference"]["axis_endpoints_px"]]
                config["horn_tip_px"]=tip
                camera_shift=native.get("quality",{}).get("camera_shift_pixels")
                camera_transform=native.get("quality",{}).get("camera_image_transform")
                if camera_transform is not None:
                    residual=native.get("quality",{}).get("body_residual_shift_pixels")
                    if (not isinstance(camera_transform,list) or len(camera_transform)!=6 or not all(finite(v) for v in camera_transform)
                            or not isinstance(residual,list) or len(residual)!=2 or not all(finite(v) for v in residual)):
                        reasons.append("invalid_camera_registration")
                    else:
                        def project(p):
                            a,b,c,d,e,f=camera_transform
                            return [a*p[0]+b*p[1]+c,d*p[0]+e*p[1]+f]
                        config["body_reference"]["axis_endpoints_px"]=[[project(p)[i]+residual[i] for i in range(2)] for p in preview_config["body_reference"]["axis_endpoints_px"]]
                        if config["preview_card"] is not None:
                            config["preview_card"]["corners_px"]=[project(p) for p in config["preview_card"]["corners_px"]]
                elif camera_shift is not None:
                    if not isinstance(camera_shift,list) or len(camera_shift)!=2 or not all(finite(v) for v in camera_shift):
                        reasons.append("invalid_camera_registration")
                    else:
                        if config["preview_card"] is not None:
                            config["preview_card"]["corners_px"]=[[p[i]+camera_shift[i] for i in range(2)] for p in config["preview_card"]["corners_px"]]
                try:
                    if reasons:raise ValueError("Invalid camera registration")
                    candidate=estimates(config)["preview_estimates"]
                    heading=candidate["apparent_image_heading_deg"]
                    if last_heading is not None and abs((heading-last_heading+180)%360-180)>policy["maximum_heading_jump_deg"]:
                        reasons.append("implausible_heading_jump")
                    else:
                        if first_heading is None:first_heading=heading
                        candidate["apparent_change_from_first_accepted_frame_deg"]=round((heading-first_heading+180)%360-180,1)
                        candidate["first_pose_is_mechanical_zero"]=False
                        preview=candidate;points={"pivot_px":pivot,"tip_px":tip};last_heading=heading
                except ValueError as exc:reasons.append("unsupported_preview_geometry: "+str(exc))
        rows.append({"frame":frame["frame"],"file":frame["file"],"sample_pts_seconds":pts,
            "host_uptime_seconds":host,"host_unix_seconds":frame.get("host_unix_seconds"),
            "status":"unknown" if reasons else "tracked_unverified","reasons":reasons,
            "localized_points":points,"preview_estimates":preview,
            "quality":native.get("quality"),"angle_deg":None,"eligible_for_verifier":False,
            "calibrated_angle_verification":False})
    return rows


def heading_summary(headings, recorded_motion=False):
    """Accepted image directions only; circular coverage is not shaft travel."""
    if type(recorded_motion) is not bool:
        raise ValueError("recorded_motion_analysis must be boolean")
    if any(not finite(v) for v in headings):
        raise ValueError("Finite image headings required")
    angles = sorted(v % 360 for v in headings)
    circular_span = None
    if angles:
        gaps = [b-a for a,b in zip(angles, angles[1:]+[angles[0]+360])]
        circular_span = 360-max(gaps)
    return {
        "recorded_motion_analysis": recorded_motion,
        "apparent_image_heading_circular_span_deg": circular_span,
        "circular_span_scope": "Shortest arc covering accepted image headings, not mechanical angle or total travelled rotation",
        "apparent_static_heading_span_deg": None if recorded_motion or not headings else max(headings)-min(headings),
        "static_span_scope": None if recorded_motion else "Repeatability on this short saved static sequence only, not angular accuracy or motion validation",
        "evaluation_scope": "Retrospective saved-motion development; not independent motion or angle verification" if recorded_motion else "Unverified static pixel localization",
    }


def track_saved(config_path, output):
    config_path,output=Path(config_path),Path(output)
    config=load(config_path)
    if config.get("mode")!="unverified_passive_tracking":raise ValueError("Explicit passive unverified mode required")
    heading_summary([], config.get("recorded_motion_analysis", False))
    preview=load(ROOT/config["preview_config"])
    if digest(ROOT/config["preview_config"])!=config["preview_config_sha256"]:raise ValueError("Preview assumptions changed; freeze a new tracking config")
    reference=ROOT/preview["reference_frame"]
    if digest(reference)!=preview["reference_sha256"]:raise ValueError("Reference image changed")
    capture=ROOT/config["source_capture"];metadata=load(capture/"capture.json")
    frames=[json.loads(line) for line in (capture/"frames.jsonl").read_text().splitlines()]
    if (metadata.get("status")!="captured" or metadata.get("source")!="live_camera"
            or metadata["camera"]["id"]!=preview["camera_id"] or not frames or len(frames)!=metadata["frame_count"]
            or [f["frame"] for f in frames]!=list(range(1,len(frames)+1))):
        raise ValueError("Consistent saved explicitly selected camera capture required")
    for f in frames:
        if f["file"]!="frame-%06d.jpg"%f["frame"]:raise ValueError("Unsafe source frame name")
    output.mkdir(parents=True,exist_ok=False)
    save(output/"tracker-config.snapshot.json",config);save(output/"preview-config.snapshot.json",preview)
    request={"reference_frame":str(reference.resolve()),"settings":config["settings"],
        "overlay_roi":preview["roi_xywh"],"digital_controls":True,
        "recorded_motion_analysis":config.get("recorded_motion_analysis",False),
        "frames":[{"id":Path(f["file"]).stem,"path":str((capture/f["file"]).resolve())}
                  for f in frames if (capture/f["file"]).is_file()]}
    save(output/"tracker.request.json",request)
    result={"status":"incomplete","angle_deg":None,"eligible_for_verifier":False,
            "servo_actuation":False,"firmware_changed":False,"serial_commands_sent":[],"meta_requests":0,
            "calibrated_angle_verification":False,"full_behavior_verification":"incomplete_required_servo_measurements_missing"}
    save(output/"tracking.json",result)
    try:
        native=subprocess.run([str(build_tracker()),str(output/"tracker.request.json"),str(output/"pixels")],capture_output=True,text=True,timeout=120)
        (output/"tracker.stderr.log").write_text(native.stderr)
        if native.returncode:raise ValueError("Native tracker failed: "+native.stderr[-2000:])
        raw=load(output/"pixels/tracked-pixels.json")
        rows=joined_trace(frames,raw,preview,config["temporal_policy"])
        for row in rows:
            file=capture/row["file"];row["source_image_sha256"]=digest(file) if file.is_file() else None
        (output/"trace.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
        controls=load(output/"pixels/digital-controls.json")
        expected={"occluded_horn","partial_horn_occlusion","blurred_horn","body_shift","body_patch_occlusion"}
        if config["settings"].get("camera_registration") is not None:
            expected|={"camera_shift_exceeds_bound","background_patch_occlusion","background_patch_disagreement"}
        controls_ok=({r["control"] for r in controls}==expected and len(controls)==len(expected)
            and all(r["status"]=="unknown" and r["pivot_px"] is None and r["tip_px"] is None for r in controls))
        accepted=[r for r in rows if r["status"]=="tracked_unverified"]
        headings=[r["preview_estimates"]["apparent_image_heading_deg"] for r in accepted]
        baseline=load(output/"pixels/baseline.json")
        result.update(status="unverified_tracking_available" if accepted and not baseline["reasons"] and controls_ok else "incomplete",
            source="automatic_pixel_localization_in_saved_live_camera_frames",
            initialization="Manually initialized ROI, body patches and hub neighborhood; per-frame pivot and tip come from image pixels",
            manual_tip_used_by_detector=False,source_capture=str(capture),frames=len(rows),tracked_frames=len(accepted),unknown_frames=len(rows)-len(accepted),
            quality_controls="pass" if controls_ok else "fail",physical_fault_injection=False,
            actual_servo_motion_tested=False,trace="trace.jsonl",
            **heading_summary(headings, config.get("recorded_motion_analysis", False)),
            assumptions=reference_notes(preview["preview_card"])+[
                "No physical angular zero, lens calibration or validated shaft angle",
                "Legacy body registration compensates translation; optional independent-background registration bounds camera transform and residual body movement separately",
                "ROI/hub neighborhood is initialized manually; not general servo discovery",
                "Rejected frames have null estimates; no interpolation or last-value reuse"],
            config_sha256=digest(config_path),source_sha256=digest(Path(__file__)),
            native_source_sha256={n:digest(ROOT/"tools/macos_servo_tracker"/n) for n in ("Tracker.swift","main.swift")})
        registration=config["settings"].get("camera_registration")
        result["registration_mode"]="independent_background_"+registration.get("model","translation") if registration else "absolute_body_translation"
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:result["error"]=str(exc)
    finally:
        save(output/"tracking.json",result)
        save(output/"integrity.json",{"sha256":{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!="integrity.json"}})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();result=track_saved(args.config,args.output)
    print(json.dumps(result,indent=2))
    return 0 if result["status"]=="unverified_tracking_available" else 2


if __name__=="__main__":raise SystemExit(main())
