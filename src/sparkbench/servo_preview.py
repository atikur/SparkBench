"""Unverified static geometry previews. Never supplies measured servo angles.

Unknown card dimensions are explicit scenario inputs, not physical calibration.
No serial, capture, network, model or firmware access is available here.
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

from .camera import ROOT
from .servo_geometry import build_helper, homography, point, project, quad
from .vision import digest, load, save


def heading(a, b):
    a,b = point(a),point(b)
    dx,dy = b[0]-a[0],b[1]-a[1]
    if math.hypot(dx,dy) < 1e-9:
        raise ValueError("Coincident points cannot define a heading")
    return math.degrees(math.atan2(dy,dx))


def inside_quad(p, corners):
    p = point(p)
    turns = [(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
             for a,b in zip(corners,corners[1:]+corners[:1])]
    return all(v>=0 for v in turns) or all(v<=0 for v in turns)


def reference_notes(card):
    """Describe reported reference provenance without upgrading calibration."""
    if card is None:
        return ["No usable planar reference in this view; image-space headings only",
                "No perspective correction or card-plane heading is available"]
    if card.get("reference_kind") in ("nominal_printed_square", "reported_square_grid"):
        size_note = ("50 x 50 mm reference grid; 1:1 geometry adopted from print design and user Measure-app report"
                     if card.get("reference_kind") == "reported_square_grid" else
                     "Nominal square printed at 100%; actual dimensions/aspect unmeasured")
        plane_note = ("User confirms flat parallel placement; not independently verified"
                      if card.get("plane_relation_confirmed") is True else
                      "Reference/horn parallelism unconfirmed; user report: " +
                      card.get("plane_alignment_report", "No current plane confirmation"))
        return [size_note, plane_note]
    return ["Card ratio is unknown; displayed ratios are illustrative",
            "User reports card only approximately parallel to horn"]


def estimates(config):
    if config.get("mode") != "unverified_static_preview":
        raise ValueError("Explicit unverified_static_preview mode required")
    origin = point(config["body_reference"]["shaft_center_px"])
    tip = point(config["horn_tip_px"])
    axis = [point(p) for p in config["body_reference"]["axis_endpoints_px"]]
    card = config["preview_card"]
    image_only = config.get("geometry_mode") == "image_only"
    if image_only and card is not None:
        raise ValueError("Image-only mode requires preview_card null")
    if card is None and not image_only:
        raise ValueError("Missing card requires explicit image_only geometry mode")
    corners = quad(card["corners_px"]) if card is not None else None
    ratios = card["illustrative_width_to_height_ratios"] if card is not None else []
    if card is not None and (not isinstance(ratios,list) or not 1<=len(ratios)<=8
            or any(type(r) not in (int,float) or not math.isfinite(r) or not .1<=r<=10 for r in ratios)
            or len(set(ratios))!=len(ratios)):
        raise ValueError("Supply 1–8 distinct positive bounded illustrative ratios")
    raw = heading(origin,tip)
    relative = (raw-heading(*axis)+180)%360-180
    scenarios = []
    for ratio in ratios:
        h = homography(corners,[[0,0],[ratio,0],[ratio,1],[0,1]])
        # An extrapolated segment crossing the projective horizon has no useful heading.
        denominators = [h[2][0]*p[0]+h[2][1]*p[1]+h[2][2] for p in (origin,tip)]
        if denominators[0]*denominators[1]<=0:
            raise ValueError("Horn segment crosses the projective horizon")
        a,b = project(h,origin),project(h,tip)
        scenarios.append({"assumed_card_width_to_height":ratio,
            "unverified_heading_from_card_top_edge_deg":round(heading(a,b),1),
            "assumed_image_to_card":h})
    return {"status":"unverified_preview_only", "eligible_for_verifier":False,
            "preview_estimates":{
                "apparent_image_heading_deg":round(raw,1),
                "image_heading_convention":"Image right = 0; positive clockwise in top-left-origin pixels",
                "apparent_horn_vs_projected_case_axis_deg":round(relative,1),
                "case_axis_scope":"Projected case direction, not a calibrated mechanical zero or confirmed horn-plane axis",
                "card_ratio_scenarios":scenarios,
                "scenarios_are_confidence_or_error_bounds":False,
                "horn_points_extrapolated_beyond_card":None if corners is None else not (inside_quad(origin,corners) and inside_quad(tip,corners))},
            "assumptions":reference_notes(card)+[
                "Shaft, tip and case landmarks are manually selected on a soft image",
                "Lens distortion and physical plane relation are unvalidated",
                *(["Horn is outside card area, so the card map is extrapolated"] if card is not None else []),
                "Mechanical angular zero and pulse-to-angle calibration are unknown"],
            "angle_deg":None,"measured_angle_calibration":None,
            "calibrated_angle_verification":False,
            "full_behavior_verification":"incomplete_required_servo_measurements_missing"}


def run(config_path, output):
    config_path,output = Path(config_path),Path(output)
    config = load(config_path)
    result = estimates(config)
    if config["preview_card"] is None:
        raise ValueError("Image-only previews use servo_tracking overlays; plane renderer requires a card")
    reference = (ROOT/config["reference_frame"]).resolve()
    if digest(reference)!=config["reference_sha256"]:
        raise ValueError("Saved reference image changed")
    capture = ROOT/config["source_capture"]
    metadata = load(capture/"capture.json")
    frames = [json.loads(line) for line in (capture/"frames.jsonl").read_text().splitlines()]
    if (metadata.get("status")!="captured" or metadata.get("source")!="live_camera"
            or metadata["camera"]["id"]!=config["camera_id"] or len(frames)!=metadata["frame_count"]):
        raise ValueError("Consistent saved camera capture required")
    if [f["frame"] for f in frames] != list(range(1,len(frames)+1)):
        raise ValueError("Camera frame IDs are incomplete")
    for f in frames:
        if f["file"]!="frame-%06d.jpg"%f["frame"] or not (capture/f["file"]).is_file():
            raise ValueError("Unsafe or missing source frame")
    ratio = config["preview_card"]["render_assumed_width_to_height"]
    if ratio not in config["preview_card"]["illustrative_width_to_height_ratios"]:
        raise ValueError("Rendered assumption must be one of the explicit scenarios")
    output.mkdir(parents=True,exist_ok=False)
    save(output/"preview-config.snapshot.json",config)
    request = {"reference_frame":str(reference),"roi":config["roi_xywh"],
        "landmarks":config["body_reference"]["landmarks"],
        "shaft_center":config["body_reference"]["shaft_center_px"],"horn_tip":config["horn_tip_px"],
        "axis":config["body_reference"]["axis_endpoints_px"],
        "frames":[{"id":Path(f["file"]).stem,"path":str(capture/f["file"])} for f in frames],
        "plane_reference":{"corners_px":config["preview_card"]["corners_px"],"plane_size":[ratio,1]},
        "preview_warning":("UNVERIFIED - 50x50mm grid plane" if config["preview_card"].get("reference_kind")=="reported_square_grid"
                           else "UNVERIFIED - assumed card ratio %.2f"%ratio)}
    save(output/"renderer.request.json",request)
    rendered = subprocess.run([str(build_helper()),str(output/"renderer.request.json"),str(output/"images")],capture_output=True,text=True,timeout=60)
    (output/"renderer.stderr.log").write_text(rendered.stderr)
    if rendered.returncode:
        raise ValueError("Preview rendering failed: "+rendered.stderr[-1500:])
    save(output/"pixel-diagnostics.json",json.loads(rendered.stdout))
    result.update(source="saved_live_camera_frame_with_manual_landmarks_and_assumed_geometry",
        source_image_sha256=digest(reference),source_config_sha256=digest(config_path),
        source_frames_sha256={f["file"]:digest(capture/f["file"]) for f in frames},
        preview_source_sha256=digest(Path(__file__)),
        renderer_source_sha256=digest(ROOT/"tools/macos_servo_geometry/main.swift"),
        rendered_card_ratio_assumption=ratio,serial_commands_sent=[],servo_actuation=False,firmware_changed=False,meta_requests=0)
    save(output/"preview.json",result)
    save(output/"integrity.json",{"sha256":{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    result = run(args.config,args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ("source_frames_sha256",)},indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
