"""whatsapp_tools on fake UI Automation trees: no WhatsApp, no clicks, no COM.

Run from the project folder: python -m unittest discover -s tests
"""
import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pc_tools  # noqa: E402
import web_control  # noqa: E402
import whatsapp_tools as wa  # noqa: E402

TYPES = {"text": wa.TEXT, "image": wa.IMAGE, "edit": wa.EDIT, "link": wa.HYPERLINK, "group": 50026,
         "row": wa.DATA_ITEM, "window": 50032, "button": 50000, "document": 50030}


def node(kind="group", name="", aid="", cls="", role="", value="", rect=(0, 0, 100, 20), children=()):
    n = wa._Node()
    n.element, n.type, n.name, n.aid, n.cls = None, TYPES[kind], name, aid, cls
    n.role, n.value, n.rect, n.children = role, value, rect, list(children)
    return n


def text(name):
    return node("text", name)


def icon(name):
    return node("image", name, rect=(0, 0, 16, 16))


def label(name):
    """The screen-reader label WhatsApp puts on a message bubble: a childless group."""
    return node(name=name)


def chat_row(title, time, preview, unread=None, top=100):
    """A chat list row as WhatsApp Desktop 2.26 shows it: the name (text and emoji images) and time
    in an inner cell, an unread count as hidden text in front of the name, the preview below."""
    head = ([text(unread)] if unread else []) + [node(children=title), node(children=[text(time)])]
    return node("row", role="row", rect=(0, top, 300, top + 70), children=[
        node("row", role="gridcell", children=[node(children=[node(children=[
            node(),  # the avatar
            node("row", role="gridcell", children=head),
            node(children=preview),
            node("row", role="gridcell"),  # badges
        ])])]),
    ])


def bubble(sender, *content):
    """A message row. The user's own carry a hidden "You:" label; in a group, someone else's start
    with a button naming them; in a one-to-one chat, theirs have neither (sender=None)."""
    head = [] if sender is None else [label("You:")] if sender == "You" else [node("button", sender)]
    return node("row", role="row", children=[node(children=[*head, *content])])


def ticks():
    return node(name="Read", children=[icon("wds-ic-read")])


def web_tree():
    """Shaped like what WhatsApp Desktop's WebView2 page exposes (from a real dump, names changed):
    page ids kept, generated CSS classes, ARIA rows, labels on the bubbles."""
    return node("document", "WhatsApp", aid="RootWebArea", children=[
        node(aid="side", children=[node("edit", "Search or start a new chat", role="textbox",
                                        rect=(10, 60, 300, 90))]),
        node(aid="pane-side", rect=(0, 90, 300, 600), children=[
            node(role="grid", name="Chat list", rect=(0, 90, 300, 9000), children=[
                chat_row([text("Annem")], "14:02", [ticks(), text("Tamam")], unread="2 unread messages", top=100),
                chat_row([text("Aile"), node("image", "🧿", cls="emoji")], "Dün",
                         [text("Ahmet"), text(":"), text("Görüşürüz")], top=170),
                chat_row([text("Ahmet Yılmaz")], "Dün", [text("Tamamdır")], top=240),
                chat_row([text("Annemarie")], "Pzt", [text("Hi")], top=700),  # scrolled out of view
            ]),
        ]),
        node(aid="main", children=[
            node(role="banner", children=[
                node("button", "Profile details", children=[node()]),
                node("button", "Ahmet Yılmaz online", children=[text("Ahmet Yılmaz"), node(children=[text("online")])]),
            ]),
            node(children=[
                node(children=[text("Use WhatsApp on your phone to see older messages.")]),
                node(children=[
                    node(children=[node(children=[text("Today")])]),
                    node(children=[bubble(None, node(children=[text("Merhaba")]), text("13:58"))]),
                    node(children=[
                        bubble("You", node(children=[text("Bak:"), node("link", "example.com", value="https://example.com/a",
                                                                          children=[text("example.com")])]),
                               node("button", "14:01 Read", children=[text("14:01"), ticks()])),
                        bubble("You", node("button", "PDF cv.pdf 2 pages • PDF • 103 kB 09:24 Read", children=[
                            text("PDF"), text("cv.pdf"), text("2 pages"), text("•"), text("103 kB"), text("09:24"), ticks()]),
                            node("button", "View"), node("button", "Save as...")),
                    ]),
                    node(children=[bubble(None, node("image", rect=(0, 0, 300, 200)), text("14:03"))]),
                    node(children=[node("row", role="row", children=[node()])]),  # not rendered yet: empty
                ]),
            ]),
            node(role="contentinfo", children=[
                node("button", "Attach"),
                node("edit", "Type a message to Ahmet Yılmaz", role="textbox", rect=(400, 900, 1200, 940)),
            ]),
        ]),
    ])


def bare_tree():
    """Without ids and labels: only roles, names and icons to go on."""
    return node("window", "WhatsApp", children=[
        node("edit", "Search", role="textbox", rect=(10, 60, 300, 90)),
        node(role="grid", name="Sohbet listesi", children=[
            node("row", role="row", children=[node(children=[text("Annem")]), text("14:02"), text("Tamam")]),
        ]),
        node(children=[
            node(role="row", children=[icon("tail-in"), text("Nasılsın?"), text("9:15 PM")]),
            node(role="row", children=[icon("tail-out"), text("İyiyim"), text("9:16 PM")]),
        ]),
    ])


class Parsing(unittest.TestCase):
    def test_chat_list(self):
        rows = wa._chat_rows(wa._chat_list(web_tree()))
        self.assertEqual([wa._chat_parts(r) for r in rows],
                         [["Annem", "14:02", "Tamam", "2 unread messages"], ["Aile 🧿", "Dün", "Ahmet: Görüşürüz"],
                          ["Ahmet Yılmaz", "Dün", "Tamamdır"], ["Annemarie", "Pzt", "Hi"]])
        self.assertEqual(wa._leaves(rows[0])[1], ["wds-ic-read"])

    def test_messages(self):
        tree = web_tree()
        messages = [wa._message(r) for r in wa._message_rows(tree)]
        self.assertEqual([m["from_me"] for m in messages], [None, False, True, True, False])
        self.assertEqual([m["time"] for m in messages], ["", "13:58", "14:01", "09:24", "14:03"])
        self.assertEqual(messages[0]["text"], "Today")
        self.assertEqual(messages[1]["text"], "Merhaba")
        self.assertEqual(messages[1]["sender"], "")
        self.assertEqual(messages[2]["text"], "Bak: example.com")
        self.assertEqual(messages[2]["links"], ["https://example.com/a"])
        self.assertEqual(messages[3]["text"], "PDF cv.pdf 2 pages • 103 kB")  # no "View", "Save as...", "You:"
        self.assertEqual(messages[3]["media"], ["document"])
        self.assertEqual(messages[4]["media"], ["photo"])
        self.assertEqual(wa._chat_title(tree), "Ahmet Yılmaz")

    def test_no_chat_open(self):
        tree = web_tree()
        tree.children = [c for c in tree.children if c.aid != "main"]
        self.assertEqual(wa._message_rows(tree), [])
        self.assertEqual(wa._chat_title(tree), "")

    def test_boxes(self):
        tree = web_tree()
        self.assertEqual(wa._search_box(tree).name, "Search or start a new chat")
        self.assertEqual(wa._compose_box(tree).name, "Type a message to Ahmet Yılmaz")

    def test_fallbacks_without_ids(self):
        tree = bare_tree()
        self.assertIsNotNone(wa._chat_list(tree))
        self.assertEqual(wa._search_box(tree).name, "Search")
        messages = [wa._message(r) for r in wa._message_rows(tree)]
        self.assertEqual([(m["from_me"], m["text"], m["time"]) for m in messages],
                         [(False, "Nasılsın?", "9:15 PM"), (True, "İyiyim", "9:16 PM")])

    def test_text_that_looks_like_an_icon_is_kept(self):
        row = bubble("Ahmet", text("follow-up"), text("10:00"))
        self.assertEqual(wa._message(row)["text"], "follow-up")

    def test_matching_row(self):
        tree = web_tree()
        original = wa._snapshot
        wa._snapshot = lambda hwnd: tree
        try:
            title = lambda row: wa._chat_parts(row)[0]
            self.assertEqual(title(wa._matching_row(0, pc_tools._normalize("ahmet yilmaz"))), "Ahmet Yılmaz")
            self.assertEqual(title(wa._matching_row(0, pc_tools._normalize("ann"))), "Annem")
            self.assertEqual(title(wa._matching_row(0, pc_tools._normalize("Aile 🧿"))), "Aile 🧿")
            self.assertIsNone(wa._matching_row(0, pc_tools._normalize("Annemarie")))  # not on screen
            self.assertIsNone(wa._matching_row(0, pc_tools._normalize("Mehmet")))
            self.assertEqual(wa._opened(0, "Ahmet Yılmaz"), "Ahmet Yılmaz")
            self.assertIsNone(wa._opened(0, "Annem"))
        finally:
            wa._snapshot = original

    def test_messages_text(self):
        data = {"chat": "Ahmet Yılmaz", "messages": [wa._message(r) for r in wa._message_rows(web_tree())]}
        out = wa._messages_text(data)
        self.assertIn("1. · Today", out)
        self.assertIn("2. ← 13:58: Merhaba", out)
        self.assertIn("3. → 14:01: Bak: example.com", out)
        self.assertIn("   🔗 https://example.com/a", out)
        self.assertIn("   📎 document", out)
        self.assertIn("   📎 photo", out)
        self.assertIn(wa.UNTRUSTED, out)

    def test_group_message(self):
        reply = bubble("Ahmet", node("button", "Quoted message", children=[
            text("Ayşe"), node("button", "0:29 Video", children=[text("0:29"), text("Video")])]),
            node(children=[node("button", "@Mert", children=[text("@"), text("Mert")]), text("bak")]), text("10:00"))
        message = wa._message(reply)
        self.assertEqual((message["from_me"], message["sender"], message["time"]), (False, "Ahmet", "10:00"))
        self.assertEqual((message["text"], message["quote"]), ("@Mert bak", "Ayşe 0:29 Video"))
        out = wa._messages_text({"chat": "Aile", "messages": [message]})
        self.assertIn("1. ← Ahmet 10:00: @Mert bak", out)
        self.assertIn("   ↪ replying to: Ayşe 0:29 Video", out)
        own = wa._message(bubble("You", text("Tamam"), node("button", "10:01 Read", children=[text("10:01"), ticks()])))
        self.assertEqual((own["from_me"], own["sender"], own["text"]), (True, "", "Tamam"))

    def test_video_reactions_and_runs_of_one_sender(self):
        video = bubble("Ayşe", node("button", "Picture-in-picture mode 0:29", children=[
            node("button", "Picture-in-picture mode"), text("0:29")]), text("08:48"),
            node("button", "Reactions ❤️ 3 in total. View reactions", children=[
                node(children=[node("image", "❤️", rect=(0, 0, 16, 16))]), node(children=[text("3")])]))
        again = bubble(None, text("Eveet"), text("08:49"))  # same sender: no name shown
        messages = wa._messages([video, again])
        self.assertEqual((messages[0]["text"], messages[0]["time"], messages[0]["media"]), ("", "08:48", ["video"]))
        self.assertEqual(messages[0]["reactions"], "❤️ 3")
        self.assertEqual([m["sender"] for m in messages], ["Ayşe", "Ayşe"])
        out = wa._messages_text({"chat": "Aile", "messages": messages})
        self.assertIn("1. ← Ayşe 08:48:\n   reactions: ❤️ 3\n   📎 video", out)


class Checks(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(wa._check_number("+44 7700 900123"), "447700900123")
        self.assertEqual(wa._check_number("0090 532 123 45 67"), "905321234567")
        with self.assertRaises(wa.ToolError):
            wa._check_number("0532 123 45 67")

    def test_send_needs_one_recipient(self):
        self.assertIn("either", wa.send_whatsapp_file("C:/x.pdf"))
        self.assertIn("either", wa.send_whatsapp_file("C:/x.pdf", phone="+447700900123", chat="Annem"))

    def test_missing_file_refused(self):
        for root in pc_tools.ALLOWED_DIRS[:1]:
            with self.assertRaises(pc_tools.ToolError):
                pc_tools._shareable_file(str(root / "no such file.pdf"))

    def test_secrets_refused(self):
        env = Path(__file__).resolve().parents[1] / ".env"
        if not env.is_file() or not any(env.is_relative_to(d) for d in pc_tools.ALLOWED_DIRS):
            self.skipTest("no .env inside the allowed folders to try with")
        with self.assertRaises(pc_tools.ToolError) as caught:
            pc_tools._shareable_file(str(env))
        self.assertIn("secret", str(caught.exception))


class Schemas(unittest.TestCase):
    def test_tools_match_functions(self):
        for module in (wa, web_control):
            names = [t["function"]["name"] for t in module.TOOLS]
            self.assertEqual(sorted(names), sorted(module.TOOL_FUNCTIONS))
            for tool in module.TOOLS:
                spec = tool["function"]
                params = inspect.signature(module.TOOL_FUNCTIONS[spec["name"]]).parameters
                self.assertTrue(set(spec["parameters"]["properties"]) <= set(params), spec["name"])
                self.assertTrue(set(spec["parameters"]["required"]) <= set(spec["parameters"]["properties"]))

    def test_no_whatsapp_web_left_in_web_control(self):
        source = Path(web_control.__file__).read_text(encoding="utf-8")
        self.assertNotIn("web.whatsapp.com", source)
        self.assertNotIn("import whatsapp_tools", source)


if __name__ == "__main__":
    unittest.main()
