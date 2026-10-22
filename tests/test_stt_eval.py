"""stt_eval: WER, the train/test split, and cutting long clips (no torch, no models).

Run from the project folder: python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import stt_eval  # noqa: E402


class WerTest(unittest.TestCase):
    def test_normalizing(self):
        self.assertEqual(stt_eval.norm_text("İstanbul'a IŞIK, Kâğıt!"), "istanbula ışık kağıt")

    def test_rates(self):
        result = stt_eval.wer([("Saat on beşte bir toplantı var", "saat 15'te bir toplantı var"),
                               ("Spotify'ı aç", "spotify ı aç")])  # 'spotifyı' -> 2 words: 2 edits
        self.assertEqual(result["clips"], 2)
        # all words: on, beşte -> 15te (2 edits) + 2 edits, over 6 + 2 words
        self.assertEqual(result["wer"], round(100 * 4 / 8, 2))
        # numbers ignored: "on", "bir" and "15te" drop out; "beşte" is still missing (1) + 2 edits,
        # over 4 + 2 words
        self.assertEqual(result["wer_ignoring_numbers"], round(100 * 3 / 6, 2))

    def test_no_words(self):
        self.assertEqual(stt_eval.wer([])["wer"], None)


class SplitTest(unittest.TestCase):
    def test_stable_and_by_sentence(self):
        samples = [{"text": f"Cümle numarası {i}."} for i in range(400)]
        samples += [{"text": "cümle numarası 3"}]  # the same sentence again, read differently
        train, test = stt_eval.split_by_sentence(samples, 0.15)
        self.assertEqual(len(train) + len(test), 401)
        self.assertTrue(30 < len(test) < 100)
        test_texts = {stt_eval.norm_text(s["text"]) for s in test}
        self.assertFalse(test_texts & {stt_eval.norm_text(s["text"]) for s in train})
        self.assertEqual(stt_eval.split_by_sentence(samples, 0.15), (train, test))


class LongClipTest(unittest.TestCase):
    def test_cuts_at_the_quiet_moment(self):
        rate = 1000
        audio = np.ones(70 * rate, dtype=np.float32) * 0.5
        audio[20 * rate:20 * rate + 500] = 0  # a pause at 20 s
        audio[45 * rate:45 * rate + 500] = 0  # and at 45 s
        cuts = stt_eval.cut_points(audio, rate)
        self.assertEqual(len(cuts), 2)
        self.assertTrue(20 * rate <= cuts[0] <= 20 * rate + 500)
        self.assertTrue(45 * rate <= cuts[1] <= 45 * rate + 500)
        pieces = np.split(audio, cuts)
        self.assertTrue(all(len(p) <= 28 * rate for p in pieces))

    def test_short_clip_is_not_cut(self):
        self.assertEqual(stt_eval.cut_points(np.ones(20 * 1000, dtype=np.float32), 1000), [])

    def test_assigns_corrected_text_to_pieces(self):
        reference = "Zyraena, telefondan yolladığım sesi aldın mı? Bunu da bilgisayardan yolluyorum."
        heard = ["zarine telefondan yolladığım sesi aldın mı", "bunu da bilgisayardan yolluyorum"]
        self.assertEqual(stt_eval.assign_words(reference, heard),
                         ["Zyraena, telefondan yolladığım sesi aldın mı?", "Bunu da bilgisayardan yolluyorum."])

    def test_drops_a_piece_that_does_not_match(self):
        reference = "bugün hava çok güzel dışarı çıkalım"
        heard = ["bugün hava çok güzel dışarı çıkalım", "tamamen alakasız başka bir konuşma burada"]
        texts = stt_eval.assign_words(reference, heard)
        self.assertEqual(texts[0], reference)
        self.assertIsNone(texts[1])

    def test_leaves_out_a_sentence_that_was_not_read(self):
        reference = ("Zyraena akşam yedide annemi aramamı hatırlat, en büyük beş dosyayı göster. "
                     "Dün gece yağmur durmadan yağdı. Sabah sokaklar hâlâ ıslaktı.")
        heard = ["dün gece yağmur durmadan yağdı", "sabah sokaklar hala ıslaktı"]
        self.assertEqual(stt_eval.assign_words(reference, heard),
                         ["Dün gece yağmur durmadan yağdı.", "Sabah sokaklar hâlâ ıslaktı."])

    def test_keeps_a_word_the_model_missed(self):
        reference = "kahvemi alıp balkona çıktım ve şehri izledim"
        self.assertEqual(stt_eval.assign_words(reference, ["kahvemi balkona çıktım ve şehri izledim"]), [reference])

    def test_an_aside_makes_the_piece_unsure(self):
        reference = "bugün hava çok güzel dışarı çıkalım akşam da sinemaya gideriz"
        heard = ["bugün hava çok güzel dışarı çıkalım", "dur bir saniye telefon çaldı akşam da sinemaya gideriz"]
        self.assertEqual(stt_eval.assign_words(reference, heard),
                         ["bugün hava çok güzel dışarı çıkalım", None])

    def test_numbers_said_as_words_are_not_an_aside(self):
        reference = "Kira on iki bin beş yüz lira. Elektrik faturası dokuz yüz seksen yedi lira geldi."
        heard = ["kira 12.500 lira", "elektrik faturası 987 lira geldi"]
        self.assertEqual(stt_eval.assign_words(reference, heard),
                         ["Kira on iki bin beş yüz lira.", "Elektrik faturası dokuz yüz seksen yedi lira geldi."])

    def test_nothing_heard(self):
        self.assertEqual(stt_eval.assign_words("bir şey", ["", ""]), [None, None])


class ReadingTest(unittest.TestCase):
    def test_sections(self):
        text = "# comment\n### 1\nBirinci satır.\n\n# not part of it\nİkinci satır.\n###2\nSon bölüm.\n### 3\n"
        self.assertEqual(stt_eval.reading_sections(text), {1: "Birinci satır. İkinci satır.", 2: "Son bölüm."})

    def test_shipped_text(self):
        path = Path(__file__).resolve().parents[1] / "voice_reading_tr.txt"
        if not path.is_file():
            self.skipTest("voice_reading_tr.txt is gitignored; not in this checkout")
        sections = stt_eval.reading_sections(path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(sections), [1, 2, 3, 4, 5, 6])
        self.assertTrue(all(len(t.split()) > 100 for t in sections.values()))

    def test_recording_names(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            for name in ("1_pc.m4a", "1_Telefon.M4A", "2.wav", "3 - laptop.mp3", "notlar.txt", "x_pc.m4a", "4_pc.docx"):
                (Path(folder) / name).write_bytes(b"")
            found = [(p.name, n, d) for p, n, d in stt_eval.user_voice_files(folder)]
        self.assertCountEqual(found, [("1_Telefon.M4A", 1, "telefon"), ("1_pc.m4a", 1, "pc"), ("2.wav", 2, "kayit"),
                                      ("3 - laptop.mp3", 3, "laptop")])

    def test_missing_folder(self):
        self.assertEqual(stt_eval.user_voice_files("C:/no/such/folder"), [])


if __name__ == "__main__":
    unittest.main()
