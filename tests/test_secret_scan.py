"""secret-scan.py: значения ловятся, имена/плейсхолдеры — нет, значения не печатаются."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("secret_scan", ROOT / "scripts" / "secret-scan.py")
ss = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["secret_scan"] = ss
spec.loader.exec_module(ss)

FAKE_AWS = "AKIA" + "IOSFODNN7EXAMPLE"  # canonical AWS doc example  # secret-scan: allow


class SecretScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-secret-scan-"))

    def scan(self) -> list[dict]:
        return ss.scan_tree(self.tmp, max_bytes=2_000_000)

    def test_planted_values_are_found_and_masked(self) -> None:
        (self.tmp / "config.toml").write_text(
            f'aws = "{FAKE_AWS}"\napp_password = "abcd efgh ijkl mnop qrst uvwx"\n',
            encoding="utf-8")
        findings = self.scan()
        rules = {f["rule"] for f in findings}
        self.assertIn("aws_access_key", rules)
        joined = json.dumps(findings, ensure_ascii=False)
        self.assertNotIn(FAKE_AWS, joined, "значение не должно попадать в отчёт целиком")

    def test_env_with_values_fails_but_names_only_example_passes(self) -> None:
        (self.tmp / ".env").write_text("WP_APP_PASSWORD=realvaluehere123\nEMPTY_ONE=\n", encoding="utf-8")
        (self.tmp / ".env.example").write_text("WP_APP_PASSWORD=\nSERPSTAT_API_KEY=\n", encoding="utf-8")
        findings = self.scan()
        self.assertTrue(any(f["rule"] == "env_value" and f["file"] == ".env" for f in findings), findings)
        self.assertFalse(any(f["file"] == ".env.example" for f in findings), findings)

    def test_allow_pragma_and_skip_dirs(self) -> None:
        (self.tmp / "docs.md").write_text(
            f"пример из документации: {FAKE_AWS}  <!-- secret-scan: allow -->\n", encoding="utf-8")
        junk = self.tmp / "node_modules" / "pkg"
        junk.mkdir(parents=True)
        (junk / "leak.js").write_text(f'key="{FAKE_AWS}"\n', encoding="utf-8")
        self.assertEqual(self.scan(), [])

    def test_private_key_block_detected(self) -> None:
        (self.tmp / "id_rsa_copy.txt").write_text(
            "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA...\n", encoding="utf-8")  # secret-scan: allow — тестовая фикстура, пишется во временный каталог, не реальный ключ
        self.assertTrue(any(f["rule"] == "private_key" for f in self.scan()))


def valid_entry(**overrides) -> dict:
    """Полная, узкая, не просроченная запись реестра — базовая фикстура для тестов.
    Переопредели только то поле, которое проверяешь на отказ."""
    entry = {
        "id": "fp-demo",
        "fingerprint": "0" * 64,
        "scope": "config.toml",
        "rule": "generic_assignment",
        "reason": "sk-packet внутри task-packet, не секрет",
        "recognized_by": "test",
        "recognized_at": "2026-08-01",
        "review_after": "2099-01-01",
    }
    entry.update(overrides)
    return entry


class FalsePositiveLedgerTest(unittest.TestCase):
    """T-021: двусторонняя сверка находок с реестром ложных срабатываний."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-secret-scan-ledger-"))
        # реалистичный ложноположительный кейс из ретро: "sk-packet" внутри слова.
        (self.tmp / "config.toml").write_text(
            'token = "task-sk-packet-not-a-real-secret-value"\n', encoding="utf-8")  # secret-scan: allow

    def scan(self) -> list[dict]:
        return ss.scan_tree(self.tmp, max_bytes=2_000_000)

    def test_ledger_suppresses_known_false_positive(self) -> None:
        findings = self.scan()
        self.assertEqual(len(findings), 1, findings)
        fp = findings[0]["fingerprint"]
        ledger = [valid_entry(fingerprint=fp)]
        active, suppressed, stale, rejected = ss.reconcile(findings, ledger)
        self.assertEqual(active, [], "покрытая находка не должна требовать разбора")
        self.assertEqual(len(suppressed), 1)
        self.assertEqual(stale, [], "запись сработала — не протухшая")
        self.assertEqual(rejected, [], "полная узкая запись обязана быть принята")

    def test_negative_control_uncovered_finding_stays_active(self) -> None:
        """Отрицательный контроль: похожая, но НЕ покрытая реестром находка обязана остаться активной."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        wrong_ledger = [valid_entry(id="fp-other", fingerprint="0" * 64)]
        self.assertNotEqual(fp, "0" * 64)
        active, suppressed, stale, rejected = ss.reconcile(findings, wrong_ledger)
        self.assertEqual(len(active), 1, "непокрытая находка обязана остаться в отчёте (скан краснеет)")
        self.assertEqual(suppressed, [])
        self.assertEqual(len(stale), 1, fp)
        self.assertEqual(rejected, [])

    def test_stale_entry_warns_when_nothing_matches_anymore(self) -> None:
        """Запись реестра, которая ни на что не совпала (код почистили), — протухшая."""
        active, suppressed, stale, rejected = ss.reconcile(
            [], [valid_entry(id="fp-dead", fingerprint="a" * 64)])
        self.assertEqual(active, [])
        self.assertEqual(suppressed, [])
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["id"], "fp-dead")
        self.assertEqual(rejected, [])

    def test_scope_glob_limits_suppression_to_matching_files(self) -> None:
        """Реестр не глобальный «на всё» — scope ограничивает подавление своим кодом (глоб по пути)."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        ledger = [valid_entry(id="fp-scoped", fingerprint=fp, scope="other/**")]
        active, suppressed, stale, rejected = ss.reconcile(findings, ledger)
        self.assertEqual(len(active), 1, "scope не совпал с файлом находки — подавлять нельзя")
        self.assertEqual(len(stale), 1)
        self.assertEqual(rejected, [])

    # --- Фикс-заход по гейту (2026-08-13): валидация записей реестра ---

    def test_entry_missing_required_field_is_rejected_not_partially_applied(self) -> None:
        """🟡№3: запись без одного из обязательных полей отвергается целиком, не подавляет ничего."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        entry = valid_entry(fingerprint=fp)
        del entry["reason"]
        active, suppressed, stale, rejected = ss.reconcile(findings, [entry])
        self.assertEqual(len(active), 1, "неполная запись не должна подавлять находку")
        self.assertEqual(suppressed, [])
        self.assertEqual(len(rejected), 1)
        self.assertIn("reason", rejected[0]["reason"])

    def test_wildcard_scope_is_rejected(self) -> None:
        """🟡№3: scope="*" — список исключений не может ослеплять весь проект целиком."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        entry = valid_entry(fingerprint=fp, scope="*")
        active, suppressed, stale, rejected = ss.reconcile(findings, [entry])
        self.assertEqual(len(active), 1, "запись со scope='*' не должна подавлять находку")
        self.assertEqual(suppressed, [])
        self.assertEqual(len(rejected), 1)

    def test_double_star_scope_is_rejected_same_as_wildcard(self) -> None:
        """fnmatch: "**" совпадает со всем деревом так же, как "*" (через "/" включительно) —
        letter-equivalent обход запрета scope="*", если бы не был отдельно отвергнут."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        entry = valid_entry(fingerprint=fp, scope="**")
        active, suppressed, stale, rejected = ss.reconcile(findings, [entry])
        self.assertEqual(len(active), 1, "запись со scope='**' не должна подавлять находку")
        self.assertEqual(suppressed, [])
        self.assertEqual(len(rejected), 1)

    # --- Повторный гейт (2026-08-14): позитивный критерий узости scope ---

    # Третий гейт (2026-08-14): батарея вырожденных форм. Путь находки —
    # "prod/.env" (тот же, на котором гейт демонстрировал пробой маской
    # "*e*"): при промахе валидации маска реально СОВПАДЁТ и находка будет
    # подавлена, то есть тест краснеет и по active, и по suppressed, а не
    # только по rejected.
    DEGENERATE_SCOPES = (
        # закрыто прошлыми кругами
        "*", "**", "*/*", "**/*", "**/**", "?*", "[a-z]*", ".*", "*[a-z]*",
        "./**", "/*", "",
        # пробой третьего гейта: буква в обёртке из звёздочек ничего не сужает
        "*e*", "*o*", "**/*e*", "[!x]*e*", "**e**", "*_*",
        "[a-z]a*", "a[a-z]*", "?a?", "**/a*", "{a,b}*", "Ω*",
        # ".." литеральным сегментом считаться не должен
        "..", "../..", "../../*e*",
        # одиночная маска без литерального сегмента — цена, названная кругом 3
        "*.env",
        # глоб на 1000+ символов
        "*" * 500 + "e" + "*" * 500,
        # ПРОБОЙ ЧЕТВЁРТОГО ГЕЙТА: литеральный сегмент есть, но НЕ первый —
        # маска привязана к ИМЕНИ файла/каталога, а не к МЕСТУ в дереве, и
        # гасит совпадение на любой глубине в любом каталоге.
        "**/.env", "*/.env", "*/prod/*", "**/x/**", "*/[a-z]/x/*",
        "**/tests/**", "?/prod/**", "[a-z]/prod/**",
        # цена якоря, названная явно: относительный префикс якорем не является
        "./prod/**", "~/prod/**",
    )

    # Пути находок подобраны так, чтобы КАЖДАЯ вырожденная форма реально
    # совпала хотя бы с одним из них: при промахе валидации тест краснеет не
    # только по `rejected`, но и по факту подавления — ровно картина гейта.
    DEGENERATE_PROBE_PATHS = (
        "prod/.env", "vendor/evil/deep/.env", "a/b/c/d/e/.env",
        "x/prod/y", "a/x/b", "src/tests/t.py", "q/a/x/z",
    )

    def test_degenerate_scope_forms_are_all_rejected(self) -> None:
        """Батарея вырожденных форм — ни одна не привязана к месту в дереве.
        Чёрный список литералов их не ловил (первый гейт), критерий «остатка
        после вычёркивания мета-символов» пробивался маской "*e*" (третий
        гейт), «хотя бы один литеральный сегмент где угодно» — маской
        "**/.env" (четвёртый). Якорь обязан отвергнуть все формы сразу,
        включая те, что никто не перечислял."""
        findings = [{"file": p, "line": "1", "rule": "generic_assignment",
                     "fingerprint": "b" * 64} for p in self.DEGENERATE_PROBE_PATHS]
        self.assertGreaterEqual(len(self.DEGENERATE_SCOPES), 24)
        for scope in self.DEGENERATE_SCOPES:
            with self.subTest(scope=scope):
                entry = valid_entry(fingerprint="b" * 64, scope=scope)
                active, suppressed, stale, rejected = ss.reconcile(findings, [entry])
                self.assertEqual(suppressed, [], f"scope={scope!r} не должен подавлять НИЧЕГО")
                self.assertEqual(len(active), len(self.DEGENERATE_PROBE_PATHS),
                                 f"scope={scope!r} обязан быть отвергнут, а не подавить находку")
                self.assertEqual(len(rejected), 1, f"scope={scope!r} обязан попасть в rejected")

    def test_nonstring_scope_is_rejected_not_a_crash(self) -> None:
        """Повторный гейт: нестроковый scope (42, True, список) раньше давал
        TypeError из fnmatch(); теперь отвергается как невалидная запись,
        без исключения, находка остаётся активной."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        for scope in (42, True, ["prod", "**"], None):
            with self.subTest(scope=scope):
                entry = valid_entry(fingerprint=fp, scope=scope)
                active, suppressed, stale, rejected = ss.reconcile(findings, [entry])
                self.assertEqual(len(active), 1)
                self.assertEqual(suppressed, [])

    # scope -> путь находки, который под этим scope обязан РЕАЛЬНО совпасть
    # (не только пройти validate_ledger_entry, но и подавиться в reconcile()).
    NARROW_SCOPE_MATCHING_PATHS = {
        "prod/**": "prod/.env",
        "prod/.env": "prod/.env",
        "prod/*.env": "prod/.env",  # форма, которую предлагает сообщение об отказе
        "docs/*.md": "docs/x.md",
        "src/**/*.py": "src/a/b.py",
        ".github/workflows/*.yml": ".github/workflows/ci.yml",
        "scripts/seo-*.py": "scripts/seo-run.py",
        "Проекты ai/example.ru/**": "Проекты ai/example.ru/prod/.env",
        "прод/**": "прод/.env",
        "Makefile": "Makefile",
        "build/Dockerfile": "build/Dockerfile",
        # якорь не должен отсечь законное (круг 4)
        "seo/**": "seo/research/raw/report.json",   # маска из демо-проекта
        "my.dir/**": "my.dir/x.txt",                # точка в имени каталога
        "a b/**": "a b/x.txt",                      # пробел в первом сегменте
        "v1.2/**": "v1.2/x.txt",                    # точки и цифры
        "_/**": "_/x.txt",                          # только подчёркивание
        "0/**": "0/x.txt",                          # только цифра
        "a/b/c/d/e/f/g/h/i/j/**": "a/b/c/d/e/f/g/h/i/j/k.txt",  # глубокая вложенность
    }

    def test_legitimate_narrow_scopes_still_suppress(self) -> None:
        """Отрицательный контроль к предыдущим двум: якорный критерий не
        должен отсекать реально узкие законные глобы — сквозная проверка
        через reconcile() (не только validate_ledger_entry/предикат:
        подавление обязано СРАБОТАТЬ, а не просто «пройти валидацию»)."""
        self.assertGreaterEqual(len(self.NARROW_SCOPE_MATCHING_PATHS), 17)
        for scope, path in self.NARROW_SCOPE_MATCHING_PATHS.items():
            with self.subTest(scope=scope):
                self.assertTrue(ss._scope_is_anchored(scope), f"{scope!r} обязан считаться узким")
                finding = {"file": path, "line": "1", "rule": "generic_assignment", "fingerprint": "b" * 64}
                entry = valid_entry(fingerprint="b" * 64, scope=scope, rule="generic_assignment")
                active, suppressed, stale, rejected = ss.reconcile([finding], [entry])
                self.assertEqual(active, [], f"scope={scope!r} обязан подавить находку {path!r}")
                self.assertEqual(len(suppressed), 1)
                self.assertEqual(rejected, [], f"scope={scope!r} — законная запись не должна отвергаться")

    def test_sha256_of_empty_string_fingerprint_is_rejected(self) -> None:
        """🟡№1 (обход из враждебного ревью): запись с fingerprint == sha256("") отвергается
        и НЕ подавляет находку без реального совпадения (например, без поля Secret у gitleaks)."""
        empty_fp = hashlib.sha256(b"").hexdigest()
        # находка без реального совпадения — как gitleaks-отчёт без поля "Secret".
        fabricated_finding = {"file": "prod/.env", "line": "1", "rule": "generic-api-key",
                               "fingerprint": empty_fp}
        entry = valid_entry(fingerprint=empty_fp, scope="prod/.env", rule="generic-api-key",
                             reason="совсем другая находка, никак не про эту")
        active, suppressed, stale, rejected = ss.reconcile([fabricated_finding], [entry])
        self.assertEqual(len(active), 1, "запись с fingerprint sha256('') не должна подавлять НИЧЕГО")
        self.assertEqual(suppressed, [], "обход воспроизведённый гейтом обязан остаться закрытым")
        self.assertEqual(len(rejected), 1)
        self.assertIn("sha256", rejected[0]["reason"])

    def test_expired_review_after_does_not_suppress_but_warns(self) -> None:
        """🟡№4: review_after — не мёртвое поле. Просроченная запись не подавляет, только предупреждает."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        entry = valid_entry(fingerprint=fp, review_after="2020-01-01")
        active, suppressed, stale, rejected = ss.reconcile(findings, [entry], today=ss.dt.date(2026, 8, 13))
        self.assertEqual(len(active), 1, "просроченная запись не должна подавлять находку")
        self.assertEqual(suppressed, [])
        self.assertEqual(len(rejected), 1)
        self.assertIn("истёк", rejected[0]["reason"])

    def test_review_after_not_yet_due_still_suppresses(self) -> None:
        """Отрицательный контроль к предыдущему: НЕ просроченная запись работает как обычно."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        entry = valid_entry(fingerprint=fp, review_after="2099-01-01")
        active, suppressed, stale, rejected = ss.reconcile(findings, [entry], today=ss.dt.date(2026, 8, 13))
        self.assertEqual(active, [])
        self.assertEqual(len(suppressed), 1)
        self.assertEqual(rejected, [])

    def test_review_after_compact_format_without_dashes_is_rejected(self) -> None:
        """💭 (advisor, повторный гейт): date.fromisoformat() принимает и
        компактный формат без дефисов ("20270101") с Python 3.11 — тише
        документированного YYYY-MM-DD (README/шаблон/сообщение об ошибке).
        Живая проверка на этом же интерпретаторе (см. «Результат»):
        dt.date.fromisoformat('20270101') == date(2027, 1, 1), без ValueError."""
        self.assertEqual(ss.dt.date.fromisoformat("20270101"), ss.dt.date(2027, 1, 1),
                          "живое подтверждение, что именно этот формат ускользнул бы от голого fromisoformat()")
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        entry = valid_entry(fingerprint=fp, review_after="20270101")
        active, suppressed, stale, rejected = ss.reconcile(findings, [entry], today=ss.dt.date(2026, 8, 13))
        self.assertEqual(len(active), 1, "компактный формат даты не должен пройти валидацию")
        self.assertEqual(suppressed, [])
        self.assertEqual(len(rejected), 1)
        self.assertIn("YYYY-MM-DD", rejected[0]["reason"])

    def test_load_ledger_missing_path_errors_and_exits_2(self) -> None:
        """Гейт T-021 (повторный заход): опечатка/битая симлинка в --ledger
        раньше молча давала пустой реестр (оператор думал, что защита
        применена) — теперь явная ошибка, exit 2, не тихий пропуск.
        Решение сознательно меняет прежнее поведение: --ledger всегда
        передаётся явно, значит опечатка в пути обязана быть слышна."""
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(buf):
            ss.load_ledger(self.tmp / "no-such.yaml")
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("ERROR", buf.getvalue())

    def test_load_ledger_unreadable_file_errors_and_exits_2(self) -> None:
        """🟡 (повторный гейт): chmod 000 — раньше голый PermissionError-
        traceback, exit 1 (OSError не ловился отдельно от yaml.YAMLError).
        Теперь читаемая ошибка + exit 2, как и для битого YAML."""
        unreadable = self.tmp / "unreadable.yaml"
        unreadable.write_text("entries: []\n", encoding="utf-8")
        unreadable.chmod(0o000)
        buf = io.StringIO()
        try:
            with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(buf):
                ss.load_ledger(unreadable)
            self.assertEqual(ctx.exception.code, 2)
            # T-090: routed through seo_cycle_core.config.load_yaml_any,
            # which reports an unreadable file with its own (still
            # coordinate/reason-bearing) message text.
            self.assertIn("ERROR", buf.getvalue())
            self.assertIn("не удалось прочитать файл", buf.getvalue())
        finally:
            unreadable.chmod(0o644)  # иначе tempfile-cleanup не сможет удалить файл

    def test_load_ledger_rejects_broken_yaml_with_error_and_exit2(self) -> None:
        """🟡№5: битый YAML — понятная ошибка и exit 2, не голый traceback."""
        bad = self.tmp / "broken.yaml"
        bad.write_text("entries: [unclosed\n", encoding="utf-8")
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(buf):
            ss.load_ledger(bad)
        self.assertEqual(ctx.exception.code, 2)
        # T-090: message now comes from load_yaml_any's own parse-error
        # reporting (coordinate-bearing, just different text).
        self.assertIn("ERROR", buf.getvalue())
        self.assertIn("столбец", buf.getvalue())

    def test_load_ledger_rejects_non_dict_top_level(self) -> None:
        """🟡№5: реестр — не объект верхнего уровня (список вместо dict)."""
        bad = self.tmp / "list-top.yaml"
        bad.write_text("- a\n- b\n", encoding="utf-8")
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(buf):
            ss.load_ledger(bad)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("ERROR: реестр нечитаем", buf.getvalue())

    def test_load_ledger_rejects_scalar_instead_of_entry(self) -> None:
        """🟡№5: скаляр вместо записи (entries: [42]) — не голый traceback на .get()."""
        bad = self.tmp / "scalar-entry.yaml"
        bad.write_text("entries:\n  - 42\n", encoding="utf-8")
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(buf):
            ss.load_ledger(bad)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("ERROR: реестр нечитаем", buf.getvalue())

    # --- Codex-ревью 2026-08-14 (P2/P3): битый реестр не смеет выглядеть ПУСТЫМ ---

    def test_load_ledger_without_entries_key_is_an_error_not_an_empty_ledger(self) -> None:
        """Опечатка в имени ключа ('entires') раньше давала тихий пустой
        реестр: «не смог прочитать» выглядело как «прочитал, и там чисто»."""
        bad = self.tmp / "typo-key.yaml"
        bad.write_text("entires:\n  - id: fp-1\n", encoding="utf-8")
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(buf):
            ss.load_ledger(bad)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("entries", buf.getvalue())

    def test_load_ledger_comments_only_is_an_error_not_an_empty_ledger(self) -> None:
        bad = self.tmp / "comments-only.yaml"
        bad.write_text("# только комментарии, ни одной записи\n", encoding="utf-8")
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(buf):
            ss.load_ledger(bad)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("entries: []", buf.getvalue())

    def test_load_ledger_entries_null_is_an_error(self) -> None:
        bad = self.tmp / "entries-null.yaml"
        bad.write_text("entries:\n", encoding="utf-8")
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(buf):
            ss.load_ledger(bad)
        self.assertEqual(ctx.exception.code, 2)

    def test_load_ledger_explicit_empty_list_is_legal(self) -> None:
        """Отрицательный контроль к трём тестам выше: ЯВНАЯ пустота —
        штатная (ровно так выглядит шаблон реестра нового проекта)."""
        ok = self.tmp / "empty-ok.yaml"
        ok.write_text("# шаблон нового проекта\nentries: []\n", encoding="utf-8")
        self.assertEqual(ss.load_ledger(ok), [])

    def test_load_ledger_non_utf8_errors_and_exits_2(self) -> None:
        """UnicodeDecodeError — подкласс ValueError, а не OSError: раньше
        реестр в чужой кодировке давал голый traceback вместо ERROR/exit 2."""
        bad = self.tmp / "cp1251.yaml"
        bad.write_bytes(b"entries: []\n# \xff\xfe\xff\n")
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(buf):
            ss.load_ledger(bad)
        self.assertEqual(ctx.exception.code, 2)
        # T-090: message now comes from load_yaml_any's own UTF-8 check.
        self.assertIn("ERROR", buf.getvalue())
        self.assertIn("не в кодировке UTF-8", buf.getvalue())

    def test_duplicate_id_does_not_hide_the_dead_twin(self) -> None:
        """🟡 четвёртого гейта / Codex P3: двусторонняя сверка ключевалась по
        "id", поэтому дубли схлопывались и совпадение одной записи навсегда
        прятало мёртвую вторую — это ровно критерий приёмки №3 тикета."""
        finding = {"file": "prod/.env", "line": "1", "rule": "generic_assignment",
                   "fingerprint": "b" * 64}
        live = valid_entry(id="fp-1", fingerprint="b" * 64, scope="prod/**")
        dead = valid_entry(id="fp-1", fingerprint="c" * 64, scope="docs/**")
        active, suppressed, stale, rejected = ss.reconcile([finding], [live, dead])
        self.assertEqual(len(suppressed), 1)
        self.assertEqual(rejected, [])
        self.assertEqual([e["scope"] for e in stale], ["docs/**"],
                         "мёртвый дубль id обязан попасть в stale")

    def test_two_entries_without_id_same_fingerprint_different_scope(self) -> None:
        """Штатный сценарий: тот же ложный текст в двух местах, записи без
        "id" — раньше обе схлопывались по общему fingerprint."""
        finding = {"file": "prod/.env", "line": "1", "rule": "generic_assignment",
                   "fingerprint": "b" * 64}
        live = valid_entry(fingerprint="b" * 64, scope="prod/**")
        dead = valid_entry(fingerprint="b" * 64, scope="docs/**")
        del live["id"], dead["id"]
        active, suppressed, stale, rejected = ss.reconcile([finding], [live, dead])
        self.assertEqual(len(suppressed), 1)
        self.assertEqual([e["scope"] for e in stale], ["docs/**"])

    def test_json_output_with_stale_entry_and_unquoted_yaml_date_does_not_crash(self) -> None:
        """Повторный гейт (НОВОЕ): --format json + протухшая запись с
        незакавыченными датами (`recognized_at: 2026-08-13` — ровно формат
        из README/шаблона) раньше падала TypeError('date is not JSON
        serializable'), потому что PyYAML парсит их в datetime.date."""
        ledger_path = self.tmp / "ledger.yaml"
        ledger_path.write_text(
            "entries:\n"
            "  - id: fp-dead\n"
            "    fingerprint: '" + "a" * 64 + "'\n"
            "    scope: nowhere/**\n"
            "    rule: generic_assignment\n"
            "    reason: тест\n"
            "    recognized_by: test\n"
            "    recognized_at: 2026-08-13\n"  # незакавычено -> yaml.date, не str
            "    review_after: 2099-01-01\n",  # незакавычено -> yaml.date, не str
            encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ss.main([str(self.tmp), "--format", "json", "--ledger", str(ledger_path)])
        payload = json.loads(buf.getvalue())  # не должно бросить TypeError при dumps внутри main()
        self.assertEqual(len(payload["stale_ledger_entries"]), 1)
        self.assertEqual(payload["stale_ledger_entries"][0]["recognized_at"], "2026-08-13")
        self.assertEqual(code, 1)

    def test_json_output_without_ledger_has_no_fingerprint_or_ledger_keys(self) -> None:
        """🔴 обратная совместимость: без --ledger JSON не содержит fingerprint/suppressed/stale_ledger_entries."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ss.main([str(self.tmp), "--format", "json"])
        self.assertEqual(code, 1)
        payload = json.loads(buf.getvalue())
        self.assertEqual(set(payload.keys()), {"findings", "count"})
        for f in payload["findings"]:
            self.assertNotIn("fingerprint", f, "без --ledger fingerprint не должен утекать в отчёт")


if __name__ == "__main__":
    unittest.main()
