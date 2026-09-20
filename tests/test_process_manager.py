from pathlib import Path
from unittest.mock import patch
import signal

import pytest

from auditor_bola.config import RuntimeConfig
from auditor_bola.process_manager import LocalTargetProcess


def _manager(tmp_path: Path, command: list[str]) -> LocalTargetProcess:
    runtime = RuntimeConfig(
        comando_inicio=command,
        directorio_trabajo=".",
        espera_inicio=0,
    )
    return LocalTargetProcess(tmp_path, runtime)


def test_resuelve_ejecutable_normal_desde_path(tmp_path):
    manager = _manager(tmp_path, ["python", "app.py"])

    with patch(
        "auditor_bola.process_manager.shutil.which",
        return_value="/usr/bin/python",
    ):
        command = manager._resolver_comando(tmp_path, {"PATH": "/usr/bin"})

    assert command == ["/usr/bin/python", "app.py"]


def test_windows_envuelve_archivo_cmd_con_cmd_exe(tmp_path):
    manager = _manager(tmp_path, ["npm", "start"])

    def fake_which(name, path=None):
        if name == "npm":
            return r"C:\Program Files\nodejs\npm.cmd"
        if name == "cmd.exe":
            return r"C:\Windows\System32\cmd.exe"
        return None

    with patch("auditor_bola.process_manager._is_windows", return_value=True), patch(
        "auditor_bola.process_manager.shutil.which",
        side_effect=fake_which,
    ):
        command = manager._resolver_comando(
            tmp_path,
            {
                "PATH": r"C:\Program Files\nodejs;C:\Windows\System32",
                "COMSPEC": r"C:\Windows\System32\cmd.exe",
            },
        )

    assert command[:5] == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
    ]
    assert command[5] == r"C:\Program Files\nodejs\npm.cmd"
    assert command[6:] == ["start"]


def test_windows_resuelve_launcher_local_gradlew_bat(tmp_path):
    launcher = tmp_path / "gradlew.bat"
    launcher.write_text("@echo off\n", encoding="utf-8")
    manager = _manager(tmp_path, ["gradlew", "bootRun"])

    with patch("auditor_bola.process_manager._is_windows", return_value=True), patch(
        "auditor_bola.process_manager.shutil.which",
        return_value=None,
    ):
        command = manager._resolver_comando(
            tmp_path,
            {
                "PATH": "",
                "PATHEXT": ".COM;.EXE;.BAT;.CMD",
                "COMSPEC": r"C:\Windows\System32\cmd.exe",
            },
        )

    assert command[:5] == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
    ]
    assert command[5].lower().endswith("gradlew.bat")
    assert command[6:] == ["bootRun"]


def test_script_python_local_usa_interprete_actual(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    manager = _manager(tmp_path, ["run.py", "--demo"])

    with patch(
        "auditor_bola.process_manager.shutil.which",
        return_value=None,
    ):
        command = manager._resolver_comando(tmp_path, {"PATH": ""})

    assert command[0]
    assert command[1] == str(script.resolve())
    assert command[2:] == ["--demo"]


def test_jar_local_se_ejecuta_con_java(tmp_path):
    jar = tmp_path / "app.jar"
    jar.write_bytes(b"demo")
    manager = _manager(tmp_path, ["app.jar", "--server.port=9000"])

    def fake_which(name, path=None):
        if name == "java":
            return "/usr/bin/java"
        return None

    with patch(
        "auditor_bola.process_manager.shutil.which",
        side_effect=fake_which,
    ):
        command = manager._resolver_comando(tmp_path, {"PATH": "/usr/bin"})

    assert command == [
        "/usr/bin/java",
        "-jar",
        str(jar.resolve()),
        "--server.port=9000",
    ]


def test_error_claro_si_comando_no_existe(tmp_path):
    manager = _manager(tmp_path, ["herramienta-inexistente", "start"])

    with patch(
        "auditor_bola.process_manager.shutil.which",
        return_value=None,
    ):
        with pytest.raises(FileNotFoundError) as exc:
            manager._resolver_comando(tmp_path, {"PATH": ""})

    assert "herramienta-inexistente" in str(exc.value)
    assert "PATH" in str(exc.value)


def test_selecciona_comando_especifico_para_windows(tmp_path):
    runtime = RuntimeConfig(
        comando_inicio=["python", "fallback.py"],
        comando_inicio_por_so={
            "windows": ["npm", "start"],
            "linux": ["bash", "start.sh"],
            "macos": ["bash", "start-macos.sh"],
        },
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch("auditor_bola.process_manager._is_windows", return_value=True):
        assert manager._command_for("inicio") == ["npm", "start"]


def test_selecciona_comando_especifico_para_macos(tmp_path):
    runtime = RuntimeConfig(
        comando_inicio=["python", "fallback.py"],
        comando_inicio_por_so={
            "macos": ["php", "-S", "127.0.0.1:8080"],
        },
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch("auditor_bola.process_manager._is_windows", return_value=False), patch(
        "auditor_bola.process_manager.sys.platform",
        "darwin",
    ):
        assert manager._command_for("inicio") == [
            "php",
            "-S",
            "127.0.0.1:8080",
        ]


def test_service_mode_usa_comandos_de_control(tmp_path):
    runtime = RuntimeConfig(
        modo="service",
        comando_inicio=["docker", "compose", "up", "-d"],
        comando_detener=["docker", "compose", "down"],
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch.object(manager, "_select_runtime_if_needed"), patch.object(
        manager,
        "_run_control_command",
    ) as run:
        manager.start()
        assert manager.is_running() is True
        assert run.call_count == 2
        assert run.call_args_list[0].args[0] == [
            "docker",
            "compose",
            "down",
        ]
        assert run.call_args_list[0].kwargs == {
            "action_name": "limpiar instancia anterior"
        }
        assert run.call_args_list[1].args[0] == [
            "docker",
            "compose",
            "up",
            "-d",
        ]
        assert run.call_args_list[1].kwargs == {
            "action_name": "iniciar"
        }

        run.reset_mock()
        manager.stop()
        assert manager.is_running() is False
        run.assert_called_once_with(
            ["docker", "compose", "down"],
            action_name="detener",
        )


def test_external_mode_no_intenta_arrancar(tmp_path):
    runtime = RuntimeConfig(modo="external")
    manager = LocalTargetProcess(tmp_path, runtime)

    with pytest.raises(RuntimeError) as exc:
        manager.start()

    assert "external" in str(exc.value)


def test_preparacion_automatica_se_ejecuta_una_sola_vez(tmp_path):
    runtime = RuntimeConfig(
        comando_inicio=["python", "app.py"],
        preparar_automaticamente=True,
        comandos_preparacion=[
            ["npm", "install"],
            ["npm", "run", "build"],
        ],
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch.object(manager, "_run_control_command") as run:
        manager._prepare_if_needed()
        manager._prepare_if_needed()

    assert run.call_count == 2
    assert manager._prepared is True


def test_error_de_arranque_incluye_salida_real_del_proceso(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text(
        "import sys\nprint('ERROR_DE_PRUEBA')\nsys.exit(1)\n",
        encoding="utf-8",
    )

    runtime = RuntimeConfig(
        comando_inicio=[str(script)],
        espera_inicio=0.2,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with pytest.raises(RuntimeError) as exc:
        manager.start()

    assert "código 1" in str(exc.value)
    assert "ERROR_DE_PRUEBA" in str(exc.value)


def test_windows_cmd_no_preescapa_comillas_de_ruta(tmp_path):
    manager = _manager(tmp_path, ["npm", "install", "--no-audit"])

    def fake_which(name, path=None):
        if name == "npm":
            return r"C:\Program Files\nodejs\npm.CMD"
        return None

    with patch("auditor_bola.process_manager._is_windows", return_value=True), patch(
        "auditor_bola.process_manager.shutil.which",
        side_effect=fake_which,
    ):
        command = manager._resolver_comando(
            tmp_path,
            {
                "PATH": r"C:\Program Files\nodejs",
                "COMSPEC": r"C:\Windows\System32\cmd.exe",
            },
        )

    assert command == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
        r"C:\Program Files\nodejs\npm.CMD",
        "install",
        "--no-audit",
    ]
    assert all('\\"' not in part for part in command)


def test_windows_detiene_arbol_completo_con_taskkill(tmp_path):
    runtime = RuntimeConfig(comando_inicio=["npm", "start"], espera_inicio=0)
    manager = LocalTargetProcess(tmp_path, runtime)

    class FakeProcess:
        pid = 4321
        def poll(self):
            return None
        def wait(self, timeout=None):
            return 0
        def terminate(self):
            raise AssertionError("no debe usar terminate si taskkill funciona")
        def kill(self):
            raise AssertionError("no debe usar kill si taskkill funciona")

    manager.process = FakeProcess()

    completed = type("Completed", (), {"returncode": 0})()

    with patch("auditor_bola.process_manager._is_windows", return_value=True), patch(
        "auditor_bola.process_manager.subprocess.run",
        return_value=completed,
    ) as run:
        manager._terminate_process_tree()

    run.assert_called_once()
    command = run.call_args.args[0]
    assert command == ["taskkill", "/PID", "4321", "/T", "/F"]


def test_posix_detiene_grupo_de_procesos(tmp_path):
    runtime = RuntimeConfig(comando_inicio=["python", "app.py"], espera_inicio=0)
    manager = LocalTargetProcess(tmp_path, runtime)

    class FakeProcess:
        pid = 9876
        def poll(self):
            return None
        def wait(self, timeout=None):
            return 0

    manager.process = FakeProcess()

    with patch("auditor_bola.process_manager._is_windows", return_value=False), patch(
        "auditor_bola.process_manager.os.getpgid",
        return_value=9876,
    ), patch(
        "auditor_bola.process_manager.os.killpg"
    ) as killpg:
        manager._terminate_process_tree()

    killpg.assert_called_once_with(9876, signal.SIGTERM)


def test_selecciona_runtime_alternativo_si_docker_no_existe(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    runtime = RuntimeConfig(
        modo="service",
        nombre="Docker Compose",
        comando_inicio=["docker", "compose", "up", "-d"],
        comando_detener=["docker", "compose", "down"],
        base_url="http://127.0.0.1:8080",
        alternativas=[
            {
                "modo": "process",
                "nombre": "Python local",
                "origen": "run.py",
                "comando_inicio": ["run.py"],
                "directorio_trabajo": ".",
                "espera_inicio": 0,
                "base_url": "http://127.0.0.1:5000",
            }
        ],
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch(
        "auditor_bola.process_manager.shutil.which",
        return_value=None,
    ):
        manager._select_runtime_if_needed()

    status = manager.runtime_status()
    assert status["nombre"] == "Python local"
    assert status["base_url"] == "http://127.0.0.1:5000"
    assert status["comando_inicio"] == ["run.py"]
    assert any(
        "Docker Compose" in item
        for item in status["alternativas_descartadas"]
    )


def test_stop_no_ejecuta_docker_si_el_arranque_nunca_funciono(tmp_path):
    runtime = RuntimeConfig(
        modo="service",
        nombre="Docker Compose",
        comando_inicio=["docker", "compose", "up", "-d"],
        comando_detener=["docker", "compose", "down"],
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch.object(manager, "_run_control_command") as run:
        manager.stop()

    run.assert_not_called()


def test_error_runtime_enumera_candidatos_no_disponibles(tmp_path):
    runtime = RuntimeConfig(
        modo="service",
        nombre="Docker Compose",
        comando_inicio=["docker", "compose", "up", "-d"],
        alternativas=[
            {
                "modo": "process",
                "nombre": "Node.js",
                "comando_inicio": ["npm", "start"],
            }
        ],
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch(
        "auditor_bola.process_manager.shutil.which",
        return_value=None,
    ):
        with pytest.raises(RuntimeError) as exc:
            manager._select_runtime_if_needed()

    message = str(exc.value)
    assert "Docker Compose" in message
    assert "Node.js" in message
    assert "docker" in message
    assert "npm" in message



def test_limpieza_previa_mata_listener_huerfano_en_puerto_local(tmp_path):
    runtime = RuntimeConfig(
        modo="process",
        nombre="Python local",
        comando_inicio=["python", "app.py"],
        base_url="http://127.0.0.1:5000",
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch.object(
        manager,
        "_terminate_stale_listener",
        return_value=[4321],
    ) as terminate:
        manager._cleanup_previous_instance()

    terminate.assert_called_once_with(5000)
    assert any(
        "4321" in note and "5000" in note
        for note in manager.runtime_status()["limpieza_previa"]
    )


def test_limpieza_previa_no_mata_puerto_de_host_remoto(tmp_path):
    runtime = RuntimeConfig(
        modo="process",
        nombre="API remota",
        comando_inicio=["python", "app.py"],
        base_url="https://api.ejemplo.com:8443",
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch.object(manager, "_terminate_stale_listener") as terminate:
        manager._cleanup_previous_instance()

    terminate.assert_not_called()


def test_start_siempre_limpia_antes_de_levantar_proceso(tmp_path):
    script = tmp_path / "run.py"
    script.write_text(
        "import time\ntime.sleep(5)\n",
        encoding="utf-8",
    )
    runtime = RuntimeConfig(
        modo="process",
        nombre="Python local",
        comando_inicio=["run.py"],
        base_url="http://127.0.0.1:5000",
        espera_inicio=0.05,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch.object(
        manager,
        "_terminate_stale_listener",
        return_value=[],
    ) as terminate:
        manager.start()
        try:
            terminate.assert_called_once_with(5000)
            assert manager.is_running() is True
        finally:
            manager.stop()



def test_cierra_todos_los_procesos_anteriores_del_mismo_proyecto(tmp_path):
    runtime = RuntimeConfig(
        modo="process",
        nombre="Python local",
        comando_inicio=["python", "run.py"],
        base_url="http://127.0.0.1:5000",
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    with patch.object(
        manager,
        "_discover_target_processes",
        return_value={2222, 3333},
    ), patch.object(
        manager,
        "_terminate_pid_tree_by_id",
        side_effect=[True, True],
    ) as terminate:
        killed = manager._terminate_all_previous_target_processes()

    assert killed == [2222, 3333]
    assert terminate.call_count == 2
    terminate.assert_any_call(2222)
    terminate.assert_any_call(3333)


def test_no_confunde_proceso_ajeno_con_el_proyecto(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    runtime = RuntimeConfig(
        modo="process",
        nombre="Python local",
        comando_inicio=["python", "run.py"],
        base_url="http://127.0.0.1:5000",
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    propio = f'python "{script}"'
    ajeno = 'python "C:/otro-proyecto/run.py"'

    assert manager._command_matches_target(propio) is True
    assert manager._command_matches_target(ajeno) is False


def test_limpieza_previa_cierra_procesos_del_proyecto_antes_del_puerto(tmp_path):
    runtime = RuntimeConfig(
        modo="process",
        nombre="Python local",
        comando_inicio=["python", "run.py"],
        base_url="http://127.0.0.1:5000",
        espera_inicio=0,
    )
    manager = LocalTargetProcess(tmp_path, runtime)

    calls = []

    def kill_project():
        calls.append("project")
        return [4444]

    def kill_port(_port):
        calls.append("port")
        return []

    with patch.object(
        manager,
        "_terminate_all_previous_target_processes",
        side_effect=kill_project,
    ), patch.object(
        manager,
        "_terminate_stale_listener",
        side_effect=kill_port,
    ):
        manager._cleanup_previous_instance()

    assert calls == ["project", "port"]
    assert any(
        "4444" in note
        for note in manager.runtime_status()["limpieza_previa"]
    )
