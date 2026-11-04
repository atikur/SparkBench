"""SAM proposals for camera setup, expressed in source image pixels."""
import base64
import re
import time

from .guide import image_bytes
from .meta import BASE_URL, configuration

MODEL = "sam-3.1"
LED_IDS = {"red": 1, "green": 2}
BOX = re.compile(
    r"(\d{1,6})<\|box;x1=(\d{1,5});y1=(\d{1,5});x2=(\d{1,5});"
    r"y2=(\d{1,5});w=(\d{1,5});h=(\d{1,5})\|>"
)
MASK = re.compile(r"<\|mask;[^>]*\|>")


def boxes_from_response(body, width, height):
    if body.get("status") != "completed":
        raise ValueError("SAM did not complete the image request.")
    try:
        parts = [part["text"] for item in body["output"] if item["type"] == "message"
                 for part in item["content"] if part["type"] == "output_text"]
        output = "".join(parts).strip()
    except (KeyError, TypeError):
        raise ValueError("SAM returned an invalid image response.") from None
    if not output:
        return {}
    if not output.startswith("<0f>"):
        raise ValueError("SAM returned an unexpected image frame.")
    records = MASK.sub("", output[4:]).split(",")
    boxes = {}
    for record in records:
        match = BOX.fullmatch(record.strip())
        if not match:
            raise ValueError("SAM returned an unsupported region.")
        label, x1, y1, x2, y2, w, h = map(int, match.groups())
        if ((w, h) != (width, height) or label in boxes
                or not (0 <= x1 < x2 < w and 0 <= y1 < y2 < h)):
            raise ValueError("SAM returned regions that do not fit this image.")
        boxes[label] = [x1, y1, x2, y2]
    return boxes


def propose_regions(body, *, config=None, post=None):
    import requests

    if set(body) != {"image", "width", "height", "points"}:
        raise ValueError("Image, dimensions and LED points required.")
    width, height = body["width"], body["height"]
    if (type(width) is not int or type(height) is not int
            or not 1 <= width <= 1920 or not 1 <= height <= 1920):
        raise ValueError("Invalid image dimensions.")
    points = body["points"]
    if not isinstance(points, dict) or (points and set(points) != set(LED_IDS)):
        raise ValueError("Click both LED lenses before outlining them.")
    prompt = "screen"
    if points:
        tokens = []
        for name, label in LED_IDS.items():
            point = points[name]
            if (not isinstance(point, list) or len(point) != 2
                    or any(type(value) is not int for value in point)
                    or not (0 <= point[0] < width and 0 <= point[1] < height)):
                raise ValueError("LED points must be inside the image.")
            x, y = point
            tokens.append(f"{label}<|point;x={x};y={y};w={width};h={height}|>")
        if points["red"] == points["green"]:
            raise ValueError("Select two separate LED lenses.")
        prompt = "<0f>" + ",".join(tokens)
    info, data = image_bytes(body["image"])
    encoded = base64.b64encode(data).decode("ascii")
    config = config or configuration()
    start = time.monotonic()
    try:
        response = (post or requests.post)(
            BASE_URL + "/responses",
            headers={"Authorization": "Bearer " + config.api_key},
            json={"model": MODEL, "stream": False, "store": False, "input": [
                {"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:{info['mime']};base64,{encoded}"},
                ]}
            ]},
            timeout=(5, 20), allow_redirects=False,
        )
    except requests.RequestException:
        raise ValueError("SAM could not be reached. Try again in a moment.") from None
    if response.status_code != 200:
        raise ValueError(f"SAM request failed (HTTP {response.status_code}).")
    try:
        reply = response.json()
    except ValueError:
        raise ValueError("SAM returned an invalid image response.") from None
    if not isinstance(reply, dict):
        raise ValueError("SAM returned an invalid image response.")
    boxes = boxes_from_response(reply, width, height)
    if points:
        regions = {}
        for name, label in LED_IDS.items():
            box = boxes.get(label)
            x, y = points[name]
            if box and box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                regions[name] = box
    else:
        regions = {"oled": next(iter(boxes.values()))} if len(boxes) == 1 else {}
    return {"model": MODEL, "image_sha256": info["sha256"], "regions": regions,
            "matches": len(boxes), "latency_seconds": round(time.monotonic() - start, 3)}
