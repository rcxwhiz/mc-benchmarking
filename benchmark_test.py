import glob
import os
import shutil
import subprocess
import time
from typing import IO, Callable, Optional

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
        # these could be better by passing self
        self.pre_test_functions: list[Callable[[], None]] = config.get("pre_test_functions", [])
        self.ready_log_line: str = config.get("ready_log_line", "textures/atlas/mob_effects.png-atlas")
        self.ready_log_interval: int = config.get("ready_log_interval", 2)
        self.ready_log_timeout: int = config.get("ready_log_timeout", 1800)
        self.log_file_path: str = config.get("log_file_path", "bench_log.txt")
        self.backup_world_path: str = config.get("backup_world_path", "world_backup")
        self.mods_path: str = config.get("mods_path", os.path.join(self.instance_path, "mods"))
        self.world_path: str = config.get("world_path", glob.glob(os.path.join(self.instance_path, "saves", "*"))[0])
        self.java_process_name: str = config.get("java_process_name", "java")
        self.window_title_key: str = config.get("window_title_key", "minecraft")
        self.mc_process_name: str = config.get("mc_process_name", "java.exe")
        self.spark_present: bool = config.get("spark_present", os.path.isdir(self.mods_path) and any("spark" in mod_file for mod_file in glob.glob(os.path.join(self.mods_path, "*.jar"))))

        self.benchmark_config: Optional["BenchmarkConfig"] = None

    def run(self, benchmark_config):
        self.benchmark_config = benchmark_config  # TODO type hinting

        self._check_for_existing_java_processes()

        if not os.path.isdir(self.instance_path):
            print(f"WARNING: instance path {self.instance_path} for test {self.test_name} is not a directory!")

        for i in range(self.n_iterations):
            print(f"Running test {self.test_name} {i+1}/{self.n_iterations}")
            self._run_iteration()

    def _check_for_existing_java_processes(self) -> None:
        existing_processes = [str(process.name) for process in psutil.process_iter(["name"]) if self.java_process_name in str(process.name)]
        if len(existing_processes) > 0:
            print(f"WARNING: Found pre-existing java processes: {existing_processes}")

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
            self._fail_wrap(self._launch_present_mon, "Failed to launch present mon")
        finally:
            self._fail_wrap(self._terminate_instance, "Failed to terminate instance (not restoring world)")
            self._fail_wrap(self._restore_world, "Failed to restore world")

    def _backup_world(self):
        shutil.copytree(self.world_path, self.backup_world_path)
    
    def _restore_world(self):
        shutil.rmtree(self.world_path)
        shutil.copytree(self.backup_world_path, self.world_path)

    def _wait_for_logline(self):
        time_started: float = time.time()
        with open(self.log_file_path, "r") as log_file:
            while time.time() - time_started < self.ready_log_timeout:
                for log_line in log_file.readlines():
                    if self.ready_log_line in log_line:
                        return
                time.sleep(self.ready_log_interval)
        raise RuntimeError(f"Didn't find \"{self.ready_log_line}\" within {self.ready_log_timeout} seconds")
    
    def _launch_instance(self) -> subprocess.Popen[bytes]:
        client_process = subprocess.Popen([self.benchmark_config.launcher_path, "--launch", self.instance_path], creationflags=subprocess.HIGH_PRIORITY_CLASS | subprocess.CREATE_NEW_CONSOLE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        return client_process
    
    def _terminate_instance(self, client_process: subprocess.Popen[bytes]):
        client_process.terminate()
        time.sleep(1)
        for proc in psutil.process_iter(['name']):
            if self.java_process_name in str(proc.name):
              print(f"Killing a hung Java process: {proc.name}")
              proc.kill()
    
    # def _terminate_present_mon(self):  # TODO move to benchmark?
    #     fininshed_proc = subprocess.run([self.benchmark_config.present_mon_path, "-terminate_existing"], creationflags = subprocess.CREATE_NEW_CONSOLE, shell=True)
    #     try:
    #         fininshed_proc.check_returncode()
    #     except Exception as e:
    #         print(f"WARNING: non-zero exit code when closing present mon: {e}")

    def _launch_present_mon(self) -> subprocess.Popen[bytes]:
        if os.path.isfile(self.benchmark_config.present_mon_csv_path):
            os.remove(self.benchmark_config.present_mon_csv_path)
        # TODO can you get the process name automatically?
        return subprocess.Popen([self.benchmark_config.present_mon_path, "-process_name", self.mc_process_name, "-output_file", self.benchmark_config.present_mon_csv_path, "-terminate_on_proc_exit"], creationflags = subprocess.CREATE_NEW_CONSOLE, shell=True)

    def _get_mc_window(self) -> pygetwindow.Win32Window:
        mc_window_title: Optional[str] = None
        for title in pygetwindow.getAllTitles():
          if self.window_title_key.lower() in title.lower():
            mc_window_title = title
        if mc_window_title is None:
            raise RuntimeError(f"Could not find Minecraft window with key {self.window_title_key}")
        return pygetwindow.getWindowsWithTitle(title)[0]
    
    def _click_play(self):
        raise NotImplementedError

    def _click_world(self):
        raise NotImplementedError
