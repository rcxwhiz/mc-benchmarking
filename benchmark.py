import logging
from benchmark_config import BenchmarkConfig
from benchmark_test import BenchmarkTest


if __name__ == "__main__":
    test = BenchmarkTest({
        "test_name": "First test",
        "instance_path": "C:/path/",
    })
    benchmark = BenchmarkConfig({
        "lanucher_path": "C:/path/",
        "tests": [test],
        "singleplayer_button_cv_images": ["image1.png", "image2.png"],
        "world_button_cv_images": ["image1.png", "image2.png"],
        "logger": logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s'),
    })
    benchmark.run()
