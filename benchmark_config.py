import os
import platform
from typing import Optional

from benchmark_test import BenchmarkTest


class BenchmarkConfig:
    def __init__(self, config: dict):
        self.launcher_path: str = config["launcher_path"]
        self.tests: list[BenchmarkTest] = config["tests"]
        self.singleplayer_button_cv_images: list[str] = config["singleplayer_button_cv_images"]
        self.world_button_cv_images: list[str] = config["world_button_cv_images"]
        self.present_mon_path: Optional[str] = config.get("present_mon_path")
        self.benchmark_results_path: str = config.get("benchmark_results_path", "benchmark_results")
        self.present_mon_csv_path: str = config.get("present_mon_csv_path", "present_mon.csv")

    def run(self):
        if platform.system() != "Windows":
            print(f"WARNING: Testing is only supported on Windows (not {platform.system()})")

        if not os.path.isfile(self.launcher_path):
            print(f"WARNING: The launcher executable path ({self.launcher_path}) is not a file!")

        for test in self.tests:
            test.run()
