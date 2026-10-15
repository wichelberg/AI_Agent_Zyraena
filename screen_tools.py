"""Tools that let Zyraena see the PC screen and send it to the user.

look_at_screen returns the screenshot to the model itself (ai_assistant attaches
it to the conversation as an image), so Zyraena can check things like "is the
video really paused?". send_screenshot sends it to the user over Telegram.
"""
import base64
import io

from PIL import ImageGrab

import pc_tools

MODEL_MAX_WIDTH = 1280  # enough to read the screen, cheap in tokens
PHOTO_MAX_WIDTH = 1920
JPEG_QUALITY = 80


def capture(max_width):
    image = ImageGrab.grab(all_screens=True).convert("RGB")
    if image.width > max_width:
        image = image.resize((max_width, round(image.height * max_width / image.width)))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def look_at_screen() -> dict:
    jpeg = capture(MODEL_MAX_WIDTH)
    return {
        "text": "Took a screenshot of the PC screen; it's attached in the next message. Answer from what you see.",
        "image": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode(),
    }


def send_screenshot(caption: str = "") -> str:
    send = pc_tools.current_photo_sender()
    if send is None:
        return "The user is at the PC (Zyraena's window), so there's nothing to send; use look_at_screen to see it yourself."
    send(capture(PHOTO_MAX_WIDTH), caption)
    return "Sent the screenshot to the user on Telegram."


def _tool(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


TOOLS = [
    _tool(
        "look_at_screen",
        "Takes a screenshot of the PC screen so you can see it. Use it to check the result of an action you "
        "can't otherwise verify (e.g. whether a video is really paused or fullscreen, what a window shows), "
        "or when the user asks what's on the screen.",
        {}, [],
    ),
    _tool(
        "send_screenshot",
        "Sends a screenshot of the PC screen to the user (over Telegram). Use when they ask to see the screen.",
        {"caption": {"type": "string", "description": "Optional short caption."}},
        [],
    ),
]

TOOL_FUNCTIONS = {"look_at_screen": look_at_screen, "send_screenshot": send_screenshot}
