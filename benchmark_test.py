import glob
import os
import shutil
import subprocess
import time
from typing import Callable, Optional

import psutil
import pygetwindow
from guibot.guibot import GuiBot 
from guibot.controller import PyAutoGUIController
from guibot.config import GlobalConfig
from guibot.finder import TemplateFinder
import pydirectinput
import pyautogui


class BenchmarkTest:
    def __init__(self, config: dict):
        self.test_name: str = config["test_name"]
        self.instance_path: str = config["instance_path"]
        self.n_iterations: int = config.get("n_iterations", 3)
        self.warmup_time: int = config.get("warmup_time", 90)
        self.benchmark_time: int = config.get("benchmark_time", 120)
        self.ready_log_line: str = config.get("ready_log_line", "textures/atlas/mob_effects.png-atlas")
        self.ready_log_interval: int = config.get("ready_log_interval", 2)
        self.ready_log_timeout: int = config.get("ready_log_timeout", 1800)
        self.backup_world_path: str = config.get("backup_world_path", "world_backup")
        self.mods_path: str = config.get("mods_path", os.path.join(self.instance_path, "mods"))
        self.world_path: str = config.get("world_path", glob.glob(os.path.join(self.instance_path, "saves", "*"))[0])
        self.java_process_name: str = config.get("java_process_name", "java")
        self.window_title_key: str = config.get("window_title_key", "minecraft")
        self.mc_process_name: str = config.get("mc_process_name", "java.exe")
        self.spark_present: bool = config.get("spark_present", os.path.isdir(self.mods_path) and any("spark" in mod_file for mod_file in glob.glob(os.path.join(self.mods_path, "*.jar"))))
        self.find_button_timeout: int = config.get("find_button_timeout", 15)
        self.look_for_button_interval: int = config.get("look_for_button_interval", 2)
        self.benchmark_interaction: Callable[[BenchmarkTest], None] = config.get("benchmark_interaction", self._benchmark_interaction)
        self.end_benchmark_interaction: Callable[[BenchmarkTest], None] = config.get("end_benchmark_interaction", self._end_benchmark_interaction)
        self.client_log_file_path: str = config.get("client_log_file_path", os.path.join(self.instance_path, "logs", "latest.log"))

        self.benchmark_config: Optional["BenchmarkConfig"] = None

    def run(self, benchmark_config):
        self.benchmark_config = benchmark_config  # TODO type hinting

        self._check_for_existing_java_processes()

        if not os.path.isdir(self.instance_path):
            self.benchmark_config.logger.warning(f"Instance path {self.instance_path} for test {self.test_name} is not a directory!")

        for i in range(self.n_iterations):
            self.benchmark_config.logger.info(f"Running test {self.test_name} {i+1}/{self.n_iterations}")
            self._run_iteration()

    def _check_for_existing_java_processes(self) -> None:
        existing_processes = [str(process.name) for process in psutil.process_iter(["name"]) if self.java_process_name in str(process.name)]
        if len(existing_processes) > 0:
            self.benchmark_config.logger.warning(f"Found pre-existing java processes: {existing_processes}")

    def _fail_wrap(self, func: Callable[[], None], error_msg: str) -> None:
        try:
            func()
        except Exception as e:
            raise RuntimeError(error_msg) from e

    def _run_iteration(self):
        self._fail_wrap(self._backup_world, "Failed to backup world")
        self._fail_wrap(self._launch_instance, "Failed to launch instance")
        try:
            self._fail_wrap(self._wait_for_logline, "Failed to wait for client log line")
            self._fail_wrap(self._click_play, "Failed to click singleplayer button")
            self._fail_wrap(self._click_world, "Failed to click world button")
            self._fail_wrap(self.benchmark_interaction, "Failed to run benchmark interaction")
            self._fail_wrap(self._let_benchmark_run, "Failed to wait for benchmark iteration to run")
            self._fail_wrap(self.end_benchmark_interaction, "Failed to run end benchmark interaction")
            self._fail_wrap(self._launch_present_mon, "Failed to launch present mon")
        finally:
            self._fail_wrap(self._terminate_instance, "Failed to terminate instance (not restoring world)")
            self._fail_wrap(self._restore_world, "Failed to restore world")

    def _backup_world(self) -> None:
        self.benchmark_config.logger.debug("Backing up world")
        shutil.copytree(self.world_path, self.backup_world_path)
    
    def _restore_world(self) -> None:
        self.benchmark_config.logger.debug("Restoring world")
        shutil.rmtree(self.world_path)
        shutil.copytree(self.backup_world_path, self.world_path)

    def _wait_for_logline(self) -> None:
        time_started: float = time.time()
        with open(self.client_log_file_path, "r") as log_file:
            while time.time() - time_started < self.ready_log_timeout:
                self.benchmark_config.logger.debug("Looking for client ready log line")
                for log_line in log_file.readlines():
                    if self.ready_log_line in log_line:
                        return
                time.sleep(self.ready_log_interval)
        raise RuntimeError(f"Didn't find \"{self.ready_log_line}\" within {self.ready_log_timeout} seconds")
    
    def _launch_instance(self) -> subprocess.Popen[bytes]:
        self.benchmark_config.logger.debug("Launching client instance")
        client_process = subprocess.Popen([self.benchmark_config.launcher_path, "--launch", self.instance_path], creationflags=subprocess.HIGH_PRIORITY_CLASS | subprocess.CREATE_NEW_CONSOLE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        return client_process
    
    def _terminate_instance(self, client_process: subprocess.Popen[bytes]) -> None:
        self.benchmark_config.logger.debug("Terminating client Java process")
        client_process.terminate()
        time.sleep(1)
        for proc in psutil.process_iter(['name']):
            if self.java_process_name in str(proc.name):
              self.benchmark_config.logger.info(f"Killing a hung Java process: {proc.name}")
              proc.kill()

    def _launch_present_mon(self) -> subprocess.Popen[bytes]:
        self.benchmark_config.logger.debug("Launching PresentMon")
        if os.path.isfile(self.benchmark_config.present_mon_csv_path):
            self.benchmark_config.logger.debug("Removing old PresentMon csv file")
            os.remove(self.benchmark_config.present_mon_csv_path)
        # TODO can you get the process name automatically?
        return subprocess.Popen([self.benchmark_config.present_mon_path, "-process_name", self.mc_process_name, "-output_file", self.benchmark_config.present_mon_csv_path, "-terminate_on_proc_exit"], creationflags = subprocess.CREATE_NEW_CONSOLE, shell=True)

    def _get_mc_window(self) -> pygetwindow.Win32Window:
        self.benchmark_config.logger.debug("Getting Mincraft client window")
        mc_window_title: Optional[str] = None
        for title in pygetwindow.getAllTitles():
          if self.window_title_key.lower() in title.lower():
            self.benchmark_config.logger.debug(f"Found Minecraft client window: {title}")
            mc_window_title = title
        if mc_window_title is None:
            raise RuntimeError(f"Could not find Minecraft window with key {self.window_title_key}")
        return pygetwindow.getWindowsWithTitle(title)[0]
    
    def _click_play(self, gui_bot: GuiBot) -> None:
        start_time: float = time.time()
        while time.time() - start_time < self.find_button_timeout:
            self.benchmark_config.logger.debug("Looking for singeplayer button")
            for singleplayer_image in self.benchmark_config.singleplayer_button_cv_images:
                if gui_bot.exists(singleplayer_image):
                    gui_bot.click(singleplayer_image)
                    return
            time.sleep(self.look_for_button_interval)
        raise RuntimeError("Could not find singleplayer button")

    def _click_world(self, gui_bot: GuiBot) -> None:
        start_time: float = time.time()
        while time.time() - start_time < self.find_button_timeout:
            self.benchmark_config.logger.debug("Looking for version (world) button")
            for world_image in self.benchmark_config.world_button_cv_images:
                if gui_bot.exists(world_image):
                    gui_bot.click(world_image)
                    return
            time.sleep(self.look_for_button_interval)
        raise RuntimeError("Could not find version (world) button")
    
    def _benchmark_interaction(self) -> None:
        pyautogui.keyDown("space")
        pyautogui.keyDown("w")
        pyautogui.mouseDown(button="left")

    def _end_benchmark_interaction(self) -> None:
        pyautogui.keyUp("space")
        pyautogui.keyUp("w")
        pyautogui.mouseUp(button="left")

    def _let_benchmark_run(self) -> None:
        time.sleep(self.benchmark_time)

    def _get_spark_info(self):
        spark_info = {
            "memory_usage": None,
            "cpu_usage": None,
            "gc_stop_ms": None,
            "gc_stops": None,
            "oldgen_gcs": None
        }
        with open(self.client_log_file_path, "r") as log_file:
            for line in log_file.readlines():
                if "Memory usage:" in line:
                    # TODO convert this to regex
                    spark_info["memory_usage"] = float(line.split("Memory usage:\n")[-1].split("GB"))
