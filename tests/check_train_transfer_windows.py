"""真实Windows三CMD验收：仅合成资产，不启动训练或接触原发布系统。"""
import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
import os
import queue
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source, tool, checks):
    if os.name != 'nt' or checks.exists():
        raise RuntimeError('必须使用Windows上的未占用合成检查目录')
    checks.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location('transfer_check', source / 'scripts/train_config_transfer.py')
    transfer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transfer)
    system = Path(os.environ['SystemRoot'])
    environment = dict(os.environ)
    environment['PATH'] = ';'.join(map(str, [system / 'System32', system, system / 'System32/WindowsPowerShell/v1.0']))
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    outcomes = []
    names = {'export': '01-导出Train配置.cmd', 'import': '02-导入Train配置.cmd', 'rollback': '03-恢复导入前Train配置.cmd'}

    def invoke(action, inputs, success=True):
        # 真实入口由cmd解释，路径通过交互stdin输入；包含复制粘贴的双引号。
        inner = subprocess.list2cmdline([str(tool / names[action])])
        command = '"' + str(system / 'System32/cmd.exe') + '" /d /s /c "' + inner + '"'
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   encoding='utf-8', errors='replace', env=environment, cwd=checks)
        characters = queue.Queue()
        def collect():
            for character in iter(lambda: process.stdout.read(1), ''):
                characters.put(character)
            characters.put(None)
        reader = threading.Thread(target=collect, daemon=True)
        reader.start()
        output, sent, paused = '', 0, False
        deadline = time.monotonic() + 90
        try:
            while True:
                if time.monotonic() >= deadline:
                    raise RuntimeError('交互CMD超时：' + output[-500:])
                try:
                    character = characters.get(timeout=.2)
                except queue.Empty:
                    continue
                if character is None:
                    break
                output += character
                if character == '：' and sent < len(inputs):
                    process.stdin.write('"' + str(inputs[sent]) + '"\n')
                    process.stdin.flush()
                    sent += 1
                if not paused and ('Press any key to continue' in output or '请按任意键继续' in output):
                    process.stdin.write('\n')
                    process.stdin.flush()
                    paused = True
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            process.stdin.close()
            process.stdout.close()
        outcomes.append({'action': action, 'expected_success': success, 'exit_code': process.returncode})
        (checks / ('cmd-%02d.log' % len(outcomes))).write_text(output, encoding='utf-8')
        if (process.returncode == 0) != success or '\ufffd' in output:
            raise RuntimeError('真实CMD结果/中文不符，见最后一个cmd日志：' + output[-600:])
        if success:
            assert {'export': 'EXPORTED', 'import': 'IMPORTED', 'rollback': 'RESTORED'}[action] in output
        return output

    def database(root, schema, populated=False):
        path = root / 'data/act_train_platform.sqlite3'
        path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(schema)
            conn.executescript("CREATE TABLE preservation(value TEXT);INSERT INTO preservation VALUES('必须保留');")
            if populated:
                conn.executescript("ALTER TABLE labels ADD COLUMN unrelated TEXT;INSERT INTO labels(code,group_code,name,description,box_instruction,enabled) VALUES('C1','C','托盘','说明','框选',1);INSERT INTO projects(id,name,product_name,sop_name,station_name,label_codes_json,notes) VALUES('p','产品配置','产品','流程','工位','[\"C1\"]','备注');")
        return path

    for version in ('v1', 'v2'):
        old, new, package = checks / (version + ' 旧act_train_platform'), checks / (version + ' 新act_train_platform'), checks / (version + ' 配置包')
        old_db = database(old, (source / ('fixtures/' + version + '.sql')).read_text(encoding='utf-8'), True)
        new_db = database(new, (source / 'fixtures/target.sql').read_text(encoding='utf-8'))
        old_hash, before = sha(old_db), sha(new_db)
        invoke('export', [old, package])
        assert sha(old_db) == old_hash
        invoke('import', [new, package])
        assert transfer.read_config(old_db) == transfer.read_config(new_db)
        with closing(sqlite3.connect(new_db)) as conn, conn:
            assert conn.execute('SELECT value FROM preservation').fetchone()[0] == '必须保留'
            assert conn.execute('SELECT count(*) FROM train_jobs').fetchone()[0] == 0
        invoke('import', [new, package])
        invoke('rollback', [new])
        invoke('rollback', [new])
        assert sha(new_db) == before
    # 以下使用最后一组独立资产验证拒绝路径，不修改任何真实配置。
    with transfer.operation_lock(new):
        assert '另一个迁移操作' in invoke('import', [new, package], False)
    invoke('import', [new, package])
    with closing(sqlite3.connect(new_db)) as conn, conn:
        conn.execute("UPDATE projects SET notes='新的配置'")
    changed = sha(new_db)
    assert '已发生变化' in invoke('rollback', [new], False)
    assert sha(new_db) == changed
    assert '不同配置' in invoke('import', [new, package], False)
    assert sha(new_db) == changed
    # 有界探针模拟目标源码服务进程身份，不进行训练；始终只结束自己创建的句柄。
    probe = old / 'app.py'
    ready = checks / 'probe.ready'
    probe.write_text("import pathlib,sys,time\npathlib.Path(sys.argv[1]).write_text('READY')\ntime.sleep(45)\n", encoding='utf-8')
    process = subprocess.Popen([sys.executable, '-B', str(probe), str(ready)], env=environment)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists() and process.poll() is None
        assert '仍在运行' in invoke('export', [old, checks / '运行中拒绝'], False)
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)
    config = package / 'train-config.json'
    with config.open('a', encoding='utf-8') as handle:
        handle.write(' ')
    assert '哈希不一致' in invoke('import', [new, package], False)
    assert sha(new_db) == changed
    result = {'status': 'PASSED', 'scope': 'synthetic-real-windows-cmd', 'commands': outcomes,
              'exe_sha256': sha(tool / 'train_config_transfer.exe'), 'external_python_required': False,
              'source_versions': ['v1.2.2.1', 'V2.0.0.1'], 'target_version': 'V2.0.0.4', 'real_site_verified': False}
    (checks / 'ACCEPTANCE.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('source', 'tool', 'checks'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.source.resolve(), args.tool.resolve(), args.checks.resolve())
