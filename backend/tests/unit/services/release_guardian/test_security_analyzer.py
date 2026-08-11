"""Unit tests for SecurityAnalyzer (WO-045)."""

from __future__ import annotations

import pytest

from forgeguard.services.release_guardian.analyzers.security_analyzer import SecurityAnalyzer
from forgeguard.services.release_guardian.models import FileChange


def _fc(filename="src/app.py", status="modified", patch="", is_binary=False, additions=0, deletions=0):
    return FileChange(
        filename=filename, status=status, patch=patch, is_binary=is_binary,
        additions=additions, deletions=deletions,
    )


class TestSecretDetection:
    def test_api_key_assignment_detected(self):
        analyzer = SecurityAnalyzer()
        patch = '+api_key = "sk_live_supersecretkey12345678"\n'
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.secrets_detected >= 1

    def test_password_assignment_detected(self):
        analyzer = SecurityAnalyzer()
        patch = '+password = "myHardcodedPassword123!"\n'
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.secrets_detected >= 1

    def test_removed_line_not_detected(self):
        analyzer = SecurityAnalyzer()
        # Lines starting with '-' are not added lines — should not be flagged
        patch = '-api_key = "sk_live_supersecretkey12345678"\n'
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.secrets_detected == 0

    def test_env_var_pattern_not_flagged(self):
        analyzer = SecurityAnalyzer()
        # Reading from env var is safe
        patch = '+api_key = os.environ.get("STRIPE_API_KEY", "")\n'
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.secrets_detected == 0

    def test_aws_access_key_detected(self):
        analyzer = SecurityAnalyzer()
        patch = '+aws_key = "AKIAIOSFODNN7EXAMPLE"\n'
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.secrets_detected >= 1

    def test_binary_file_skipped(self):
        analyzer = SecurityAnalyzer()
        fc = _fc(patch='+api_key = "sk_live_secretkey12345678"\n', is_binary=True)
        result = analyzer.analyze([fc])
        assert result.secrets_detected == 0


class TestSQLPatternDetection:
    def test_string_concatenation_detected(self):
        analyzer = SecurityAnalyzer()
        patch = '+query = "SELECT * FROM users WHERE name = \'" + user_input + "\'"\n'
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.sql_patterns_detected >= 1

    def test_fstring_sql_detected(self):
        analyzer = SecurityAnalyzer()
        patch = '+cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")\n'
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.sql_patterns_detected >= 1

    def test_parameterized_query_not_flagged(self):
        analyzer = SecurityAnalyzer()
        patch = '+cursor.execute("SELECT * FROM users WHERE id = $1", user_id)\n'
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.sql_patterns_detected == 0


class TestUnsafeDeserialization:
    def test_pickle_loads_detected(self):
        analyzer = SecurityAnalyzer()
        patch = "+result = pickle.loads(data)\n"
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.unsafe_deserialization_detected >= 1

    def test_eval_detected(self):
        analyzer = SecurityAnalyzer()
        patch = "+result = eval(user_input)\n"
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.unsafe_deserialization_detected >= 1

    def test_exec_detected(self):
        analyzer = SecurityAnalyzer()
        patch = "+exec(user_code)\n"
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.unsafe_deserialization_detected >= 1

    def test_safe_json_loads_not_flagged(self):
        analyzer = SecurityAnalyzer()
        patch = "+data = json.loads(payload)\n"
        result = analyzer.analyze([_fc(patch=patch)])
        assert result.unsafe_deserialization_detected == 0


class TestSecurityConfigChanges:
    def test_env_file_detected(self):
        analyzer = SecurityAnalyzer()
        fc = _fc(filename=".env", patch="")
        result = analyzer.analyze([fc])
        assert ".env" in result.security_config_changes

    def test_pem_file_detected(self):
        analyzer = SecurityAnalyzer()
        fc = _fc(filename="config/server.pem", patch="")
        result = analyzer.analyze([fc])
        assert "config/server.pem" in result.security_config_changes

    def test_normal_python_file_not_config(self):
        analyzer = SecurityAnalyzer()
        fc = _fc(filename="src/app.py", patch="")
        result = analyzer.analyze([fc])
        assert "src/app.py" not in result.security_config_changes
