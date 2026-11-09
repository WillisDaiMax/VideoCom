"""预估模型：参数来自实测，结果应落在合理范围。"""
import unittest

from videocom import config, estimate

G = 2 ** 30


class Estimate(unittest.TestCase):
    def setUp(self):
        self.cfg = config._merge(config.DEFAULTS, {})
        estimate.HISTORY = estimate.Path("/nonexistent/history.json")   # 不读本机历史

    def probe(self, size, dur=7200, codec="h264", w=1920, h=1080, fps=23.976):
        return {"size": size, "duration": dur, "width": w, "height": h, "fps": fps, "codec": codec,
                "vbitrate": size * 8 / dur * 0.88}

    def test_high_bitrate_movie_is_capped(self):
        r = estimate.estimate(self.cfg, "movie", "compress", self.probe(7.06 * G))
        self.assertLess(r["ratio"], 0.45)
        self.assertGreater(r["value"], 0)

    def test_low_bitrate_movie_gains_less(self):
        hi = estimate.estimate(self.cfg, "movie", "compress", self.probe(7.06 * G))
        lo = estimate.estimate(self.cfg, "movie", "compress", self.probe(1.17 * G))
        self.assertGreater(lo["ratio"], hi["ratio"])
        self.assertGreater(hi["value"], lo["value"])

    def test_never_larger_than_source(self):
        r = estimate.estimate(self.cfg, "daily", "compress", self.probe(50 * 2 ** 20, dur=60, codec="hevc"))
        self.assertLessEqual(r["out_size"], 50 * 2 ** 20)

    def test_remux_keeps_size(self):
        r = estimate.estimate(self.cfg, "daily", "remux", self.probe(G))
        self.assertEqual(r["ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
