"""Passive geometry only: no serial, capture, model calls or firmware access.

Image-space body coordinates and calibrated plane coordinates are separate.
A rectangular-looking case silhouette is not a metric plane calibration.
"""
import argparse
import json
import math
import platform
import shutil
import subprocess
from pathlib import Path

from .camera import ROOT
from .vision import digest, load, save


def point(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise ValueError("Expected a finite 2D point")
    return [float(v) for v in value]


def multiply(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def solve(a, b):
    n = len(b)
    rows = [list(a[i])+[b[i]] for i in range(n)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda i: abs(rows[i][column]))
        if abs(rows[pivot][column]) < 1e-12:
            raise ValueError("Degenerate geometry")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        scale = rows[column][column]
        rows[column] = [v/scale for v in rows[column]]
        for i in range(n):
            if i == column:
                continue
            scale = rows[i][column]
            rows[i] = [v-scale*w for v,w in zip(rows[i], rows[column])]
    return [r[-1] for r in rows]


def project(matrix, value):
    x, y = point(value)
    v = [sum(row[k]*[x,y,1][k] for k in range(3)) for row in matrix]
    if not all(math.isfinite(t) for t in v) or abs(v[2]) < 1e-12:
        raise ValueError("Point projects to infinity")
    return [v[0]/v[2], v[1]/v[2]]


def quad(values):
    if not isinstance(values, list) or len(values) != 4:
        raise ValueError("Four ordered planar corners required")
    values = [point(p) for p in values]
    turns = []
    for i in range(4):
        a,b,c = values[i],values[(i+1)%4],values[(i+2)%4]
        turns.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
    if not (all(v > 1e-8 for v in turns) or all(v < -1e-8 for v in turns)):
        raise ValueError("Corners must form a nondegenerate convex ordered quadrilateral")
    return values


def normalize(values):
    center = [sum(p[i] for p in values)/len(values) for i in range(2)]
    spread = sum(math.hypot(p[0]-center[0],p[1]-center[1]) for p in values)/len(values)
    if spread < 1e-12:
        raise ValueError("Coincident geometry")
    scale = math.sqrt(2)/spread
    transform = [[scale,0,-scale*center[0]],[0,scale,-scale*center[1]],[0,0,1]]
    inverse = [[1/scale,0,center[0]],[0,1/scale,center[1]],[0,0,1]]
    return [project(transform,p) for p in values],transform,inverse


def homography(source, destination):
    """Four-point map with centered/scaled coordinates for numerical stability."""
    source,destination = quad(source),quad(destination)
    src,source_t,_ = normalize(source)
    dst,_,destination_inverse = normalize(destination)
    rows,targets = [],[]
    for (x,y),(u,v) in zip(src,dst):
        rows.extend(([x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]))
        targets.extend((u,v))
    h = solve(rows,targets)+[1]
    result = multiply(multiply(destination_inverse,[h[:3],h[3:6],h[6:]]),source_t)
    scale = result[2][2]
    if abs(scale) < 1e-12:
        scale = max(abs(v) for row in result for v in row)
    result = [[v/scale for v in row] for row in result]
    if max(math.dist(project(result,s),d) for s,d in zip(source,destination)) > 1e-6:
        raise ValueError("Homography correspondence check failed")
    return result


def body_coordinates(origin, axis_start, axis_end):
    """Translate/rotate image pixels only; not correction of optical perspective."""
    origin,start,end = point(origin),point(axis_start),point(axis_end)
    dx,dy = end[0]-start[0],end[1]-start[1]
    length = math.hypot(dx,dy)
    if length < 20:
        raise ValueError("Body reference axis is too short")
    dx,dy = dx/length,dy/length
    return [[dy,-dx,-dy*origin[0]+dx*origin[1]],
            [dx,dy,-dx*origin[0]-dy*origin[1]],[0,0,1]]


def perspective(reference):
    """A known metric plane and its relation to the horn must be explicit."""
    missing = {"status":"incomplete", "image_to_plane":None,
               "reason":"No confirmed metric plane parallel to the horn rotation plane",
               "angle_deg":None, "calibrated_angle_verification":False}
    if reference is None:
        return missing
    if not isinstance(reference,dict):
        raise ValueError("Planar reference must be an object")
    if (reference.get("dimensions_confirmed") is not True
            or reference.get("plane_relation_confirmed") is not True
            or reference.get("relation_to_horn_plane") not in ("same_plane","parallel_plane")
            or not isinstance(reference.get("provenance"),str) or not reference["provenance"].strip()):
        return missing
    size = point(reference.get("plane_size"))
    if any(v <= 0 for v in size):
        raise ValueError("Positive known plane dimensions or aspect ratio required")
    corners = quad(reference.get("corners_px"))
    matrix = homography(corners,[[0,0],[size[0],0],size,[0,size[1]]])
    return {"status":"reference_defined_pending_independent_validation",
            "image_to_plane":matrix, "plane_size":size,
            "reference_provenance":reference["provenance"],
            "angle_deg":None, "calibrated_angle_verification":False,
            "limits":"Corner reprojection is an algebra check, not physical accuracy validation. Lens distortion, plane relation, angular zero and moving-body tracking still require qualification."}


def build_helper():
    if platform.system() != "Darwin" or not shutil.which("xcrun"):
        raise ValueError("Passive rendering requires macOS command-line tools")
    source = ROOT/"tools/macos_servo_geometry/main.swift"
    folder = ROOT/".cache/servo_geometry"
    folder.mkdir(parents=True,exist_ok=True)
    binary,stamp = folder/"StaticBodyReference",folder/"source.sha256"
    fingerprint = digest(source)+platform.machine()+platform.mac_ver()[0]
    if not (binary.is_file() and stamp.is_file() and stamp.read_text()==fingerprint):
        result = subprocess.run(["xcrun","swiftc","-O","-module-cache-path",str(folder/"swift-modules"),str(source),"-o",str(binary)],capture_output=True,text=True,timeout=120)
        if result.returncode:
            raise ValueError("Passive renderer build failed: "+result.stderr[-2000:])
        stamp.write_text(fingerprint)
    return binary


def establish(config_path, output):
    config_path,output = Path(config_path),Path(output)
    config = load(config_path)
    reference = (ROOT/config["reference_frame"]).resolve()
    if digest(reference) != config["reference_sha256"]:
        raise ValueError("Reference frame changed")
    origin = config["body_reference"]["shaft_center_px"]
    axis = config["body_reference"]["axis_endpoints_px"]
    image_to_body = body_coordinates(origin,*axis)
    plane = perspective(config.get("plane_reference"))
    capture = ROOT/config["source_capture"]
    report = load(capture/"capture.json")
    if report.get("source") != "live_camera" or report.get("status") != "captured" or report["camera"]["id"] != config["camera_id"]:
        raise ValueError("Completed explicitly selected camera capture required")
    frames = [json.loads(line) for line in (capture/"frames.jsonl").read_text().splitlines()]
    if not frames or len(frames)!=report["frame_count"]:
        raise ValueError("Incomplete camera frame journal")
    for frame in frames:
        if frame["file"] != "frame-%06d.jpg" % frame["frame"] or not (capture/frame["file"]).is_file():
            raise ValueError("Unsafe or missing source frame")
    output.mkdir(parents=True,exist_ok=False)
    save(output/"geometry.snapshot.json",config)
    request = {"reference_frame":str(reference),"roi":config["roi_xywh"],
               "landmarks":config["body_reference"]["landmarks"],
               "shaft_center":origin,"horn_tip":config["horn_tip_px"],"axis":axis,
               "frames":[{"id":Path(f["file"]).stem,"path":str(capture/f["file"])} for f in frames],
               "plane_reference":config.get("plane_reference") if plane["image_to_plane"] else None}
    save(output/"renderer.request.json",request)
    result = subprocess.run([str(build_helper()),str(output/"renderer.request.json"),str(output/"images")],capture_output=True,text=True,timeout=60)
    (output/"renderer.stderr.log").write_text(result.stderr)
    if result.returncode:
        raise ValueError("Passive renderer failed: "+result.stderr[-2000:])
    metrics = json.loads(result.stdout)
    save(output/"pixel-diagnostics.json",metrics)
    value = {"schema_version":1,"status":"body_image_reference_established_perspective_incomplete" if plane["image_to_plane"] is None else "plane_reference_defined_validation_pending",
             "source":"saved_live_camera_frames_with_agent_selected_landmarks",
             "reference_sha256":digest(reference),"image_to_body_pixels":image_to_body,
             "body_reference_scope":"Translation/rotation of image pixels only; projected case axis is not a calibrated mechanical zero or horn-plane axis",
             "perspective":plane,"angle_deg":None,"calibrated_angle_verification":False,
             "frames_checked":len(frames),"source_frames_sha256":{f["file"]:digest(capture/f["file"]) for f in frames},
             "renderer_source_sha256":digest(ROOT/"tools/macos_servo_geometry/main.swift"),
             "geometry_source_sha256":digest(Path(__file__)),
             "serial_commands_sent":[],"servo_actuation":False,"firmware_changed":False,
             "meta_requests":0,"full_behavior_verification":"incomplete_required_servo_measurements_missing"}
    save(output/"reference.json",value)
    save(output/"integrity.json",{"sha256":{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    result = establish(args.geometry,args.output)
    print(json.dumps(result,indent=2))
    return 0  # Reference artifact creation succeeded; calibration status is explicit.


if __name__=="__main__": raise SystemExit(main())
