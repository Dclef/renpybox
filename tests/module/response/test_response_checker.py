import unittest

from base.BaseLanguage import BaseLanguage
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Response.ResponseChecker import ResponseChecker


def build_partial_mixed_translation() -> tuple[str, str]:
    src = "{cps=0}{color=#ba0724}[u]:{/color}{/cps} Damn, I'm still dead tired..."
    dst = (
        "{cps=0}{color=#ba0724}[u]:{/color}{/cps} "
        + chr(0x5929) + "amn" + chr(0xFF0C) + " "
        + chr(0x6211) + "m s" + chr(0x771F) + "ll "
        + chr(0x662F) + "ea "
        + chr(0x7D2F) + "e" + chr(0x4E86) + "..."
    )
    return src, dst


class ResponseCheckerMixedLanguageTests(unittest.TestCase):

    def build_config(self) -> Config:
        config = Config()
        config.source_language = BaseLanguage.Enum.EN
        config.target_language = BaseLanguage.Enum.ZH
        return config

    def test_detects_mixed_language_leakage(self) -> None:
        src, dst = build_partial_mixed_translation()

        self.assertTrue(ResponseChecker.has_mixed_language_leakage(src, dst))

        item = CacheItem(src = src, text_type = CacheItem.TextType.RENPY)
        checks = ResponseChecker(self.build_config(), [item]).check(
            [src],
            [dst],
            CacheItem.TextType.RENPY,
        )

        self.assertEqual(
            checks,
            [ResponseChecker.Error.LINE_ERROR_MIXED_LANGUAGE],
        )

    def test_mixed_language_error_is_not_relaxed_after_retry_threshold(self) -> None:
        src, dst = build_partial_mixed_translation()

        item = CacheItem(src = src, text_type = CacheItem.TextType.RENPY)
        item.set_retry_count(ResponseChecker.RETRY_COUNT_THRESHOLD)
        checks = ResponseChecker(self.build_config(), [item]).check(
            [src],
            [dst],
            CacheItem.TextType.RENPY,
        )

        self.assertEqual(
            checks,
            [ResponseChecker.Error.LINE_ERROR_MIXED_LANGUAGE],
        )

    def test_allows_expected_proper_nouns_and_acronyms(self) -> None:
        self.assertFalse(
            ResponseChecker.has_mixed_language_leakage(
                "Meet Stacy tomorrow.",
                chr(0x660E) + chr(0x5929) + chr(0x53BB) + chr(0x89C1) + "Stacy" + chr(0x5427),
            )
        )
        self.assertFalse(
            ResponseChecker.has_mixed_language_leakage(
                "USB cable connected.",
                "USB" + chr(0x63A5) + chr(0x53E3) + chr(0x5DF2) + chr(0x8FDE) + chr(0x63A5),
            )
        )
        self.assertFalse(
            ResponseChecker.has_mixed_language_leakage(
                "iPhone is expensive.",
                chr(0x6211) + chr(0x559C) + chr(0x6B22) + "iPhone" + chr(0x624B) + chr(0x673A),
            )
        )


if __name__ == "__main__":
    unittest.main()
