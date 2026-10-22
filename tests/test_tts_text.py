"""tts_text: Turkish numbers, respelled names and sentence cutting for the local TTS.

Run from the project folder: python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tts_text  # noqa: E402


class NumberTest(unittest.TestCase):
    def test_words(self):
        cases = {0: "sıfır", 7: "yedi", 10: "on", 17: "on yedi", 100: "yüz", 101: "yüz bir", 250: "iki yüz elli",
                 1000: "bin", 1250: "bin iki yüz elli", 2026: "iki bin yirmi altı", 12500: "on iki bin beş yüz",
                 100000: "yüz bin", 1000000: "bir milyon", 3000000000: "üç milyar"}
        for n, words in cases.items():
            self.assertEqual(tts_text.number_words(n), words, n)

    def test_in_text(self):
        cases = {
            "Saat 17:30'da toplantın var.": "Saat on yedi otuzda toplantın var.",
            "Saat 9:05.": "Saat dokuz beş.",
            "Saat 14:00'te": "Saat on dört sıfır sıfırte",
            "Sesi %30'a indirdim.": "Sesi yüzde otuza indirdim.",
            "Fiyatı 1.250 lira.": "Fiyatı bin iki yüz elli lira.",
            "Dosya 3,4 GB, model 2.5 kat hızlı.": "Dosya üç virgül dört GB, model iki virgül beş kat hızlı.",
            "3,05 saniye": "üç virgül sıfır beş saniye",
            "5'te gel, 82 derece.": "beşte gel, seksen iki derece.",
        }
        for text, said in cases.items():
            self.assertEqual(tts_text.say_numbers(text), said, text)


class RespellTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(tts_text.respell("Claude Code'un değişiklikleri hazır, Spotify'ı açtım."),
                         "Klod Kodun değişiklikleri hazır, Spotifayı açtım.")
        self.assertEqual(tts_text.respell("Claude ile konuştum"), "Klod ile konuştum")

    def test_whole_words_only(self):
        self.assertEqual(tts_text.respell("AIRA ve Steamer"), "AIRA ve Steamer")

    def test_prepare(self):
        self.assertEqual(tts_text.prepare("  GPU 82   derece,\n%5 yük. "), "ci pi yu seksen iki derece, yüzde beş yük.")


class SentenceTest(unittest.TestCase):
    def test_cut_and_join(self):
        text = "Tamam. Spotify'ı açtım ve sesi yüzde otuza indirdim! Başka bir isteğin var mı?\nHazırım."
        self.assertEqual(tts_text.sentences(text),
                         ["Tamam. Spotify'ı açtım ve sesi yüzde otuza indirdim!",
                          "Başka bir isteğin var mı? Hazırım."])

    def test_long_sentence_is_cut_at_commas(self):
        text = ", ".join(["bu uzun cümlenin bir parçası daha"] * 12) + "."
        pieces = tts_text.sentences(text)
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(p) <= tts_text.MAX_CHARS for p in pieces))
        self.assertEqual(" ".join(pieces), text)

    def test_empty(self):
        self.assertEqual(tts_text.sentences("  \n "), [])


class QuickStartTest(unittest.TestCase):
    def test_short_first_sentence_stays(self):
        text = "Hava bugün çok güzel. Dışarı çıkacaksan şemsiyeni yine de yanına al, yüzey sakini."
        self.assertEqual(tts_text.sentences(text), ["Hava bugün çok güzel.",
                                                    "Dışarı çıkacaksan şemsiyeni yine de yanına al, yüzey sakini."])

    def test_first_piece_is_cut_at_its_first_comma(self):
        text = "Hava bugün parçalı bulutlu, öğleden sonra yağmur bekleniyor. Şemsiyeni yanına almayı unutma."
        self.assertEqual(tts_text.sentences(text), ["Hava bugün parçalı bulutlu,", "öğleden sonra yağmur bekleniyor.",
                                                    "Şemsiyeni yanına almayı unutma."])

    def test_a_comma_too_early_is_skipped(self):
        pieces = tts_text.sentences("Tamam, dosyaları yedek klasörüne taşıdım, hiçbiri kaybolmadı, hepsi yerinde.")
        self.assertEqual(pieces, ["Tamam, dosyaları yedek klasörüne taşıdım,", "hiçbiri kaybolmadı, hepsi yerinde."])

    def test_a_comma_that_leaves_too_little_is_skipped(self):
        text = "Tamam, Spotify'ı açtım ve sesi biraz kıstım, hazır."
        self.assertEqual(tts_text.sentences(text), [text])

    def test_without_a_comma_it_is_cut_after_some_words(self):
        text = "Dosyaları masaüstündeki yedek klasörüne tek tek taşıdım ve hepsini dikkatlice kontrol ettim."
        pieces = tts_text.sentences(text)
        self.assertEqual(len(pieces[0].split()), tts_text.FIRST_CUT)
        self.assertEqual(" ".join(pieces), text)

    def test_the_rest_is_never_tiny(self):
        text = "Dosyaları masaüstündeki yedek klasörüne tek tek taşıdım ve kontrol ettim."  # 10 words
        pieces = tts_text.sentences(text)
        self.assertGreaterEqual(len(pieces[1].split()), tts_text.FIRST_WORDS[0])
        self.assertEqual(" ".join(pieces), text)

    def test_a_long_rest_is_cut_at_a_comma(self):
        text = ("Bunu hallettim küçük olan, dosyaların hepsini masaüstündeki yedek klasörüne taşıdım, "
                "toplam on iki dosya vardı ve hiçbiri kaybolmadı.")
        self.assertEqual(tts_text.sentences(text), [
            "Bunu hallettim küçük olan,", "dosyaların hepsini masaüstündeki yedek klasörüne taşıdım,",
            "toplam on iki dosya vardı ve hiçbiri kaybolmadı."])

    def test_no_piece_is_much_longer_than_the_one_before(self):
        text = ("Günün bu erken saatinde öncelikle biraz dinlenmek ya da uyumak iyi bir fikir olabilir. Ama uyanıksan "
                "ve gününü planlamak istiyorsan, yarım kalan işlerine göz atabilir, biraz oyun oynayıp kafa "
                "dağıtabilir ya da yeni bir şeyler öğrenebilirsin. Nasıl bir moddasın?")
        pieces = tts_text.sentences(text)
        self.assertEqual(pieces[2:5], ["Ama uyanıksan ve gününü planlamak istiyorsan,", "yarım kalan işlerine göz atabilir,",
                                       "biraz oyun oynayıp kafa dağıtabilir ya da yeni bir şeyler öğrenebilirsin. Nasıl bir moddasın?"])
        self.assertEqual(" ".join(pieces), text)

    def test_nothing_is_lost(self):
        text = ("Tamam, Spotifayı açtım ve sesi biraz kıstım, toplantın on yedi otuzda başlıyor, o yüzden yarım "
                "saatin var. Başka bir şey ister misin?")
        pieces = tts_text.sentences(text)
        self.assertLessEqual(len(pieces[0].split()), tts_text.FIRST_WORDS[1])
        self.assertEqual(" ".join(pieces), text)


if __name__ == "__main__":
    unittest.main()
