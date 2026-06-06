import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import OperationalError
from backend.app.db.session import check_alembic_head
import logging

@pytest.fixture
def mock_alembic_env():
    with patch('alembic.config.Config') as mock_config, \
         patch('alembic.script.ScriptDirectory') as mock_script_dir, \
         patch('backend.app.db.session.sync_engine') as mock_engine, \
         patch('alembic.runtime.migration.MigrationContext') as mock_migration_context, \
         patch('time.sleep') as mock_sleep: # Mock sleep to speed up retry tests
        
        # Setup ScriptDirectory mock
        mock_script_instance = MagicMock()
        mock_script_dir.from_config.return_value = mock_script_instance
        
        # Setup Connection mock
        mock_connection = MagicMock()
        mock_engine.connect.return_value = mock_connection
        mock_connection.__enter__ = MagicMock(return_value=mock_connection)
        mock_connection.__exit__ = MagicMock(return_value=False)
        
        # Setup MigrationContext mock
        mock_context_instance = MagicMock()
        mock_migration_context.configure.return_value = mock_context_instance
        
        yield {
            'script': mock_script_instance,
            'context': mock_context_instance,
            'engine': mock_engine
        }

def test_schema_validation_success(caplog, mock_alembic_env):
    caplog.set_level(logging.INFO)
    mock_alembic_env['script'].get_heads.return_value = ["abcd1234efgh"]
    mock_alembic_env['context'].get_current_heads.return_value = ["abcd1234efgh"]
    
    check_alembic_head()
    
    assert "STARTUP STEP: DATABASE CONNECTIVITY" in caplog.text
    assert "STARTUP STEP: ALEMBIC VALIDATION" in caplog.text
    assert "STARTUP STEP: APPLICATION READY" in caplog.text

def test_schema_validation_failure(caplog, mock_alembic_env):
    caplog.set_level(logging.INFO)
    mock_alembic_env['script'].get_heads.return_value = ["abcd1234efgh"]
    mock_alembic_env['context'].get_current_heads.return_value = ["old_revision"]
    
    with pytest.raises(RuntimeError, match="SCHEMA VALIDATION FAILED"):
        check_alembic_head()
        
    assert "Refusing startup." in caplog.text
    assert "Application must terminate." in caplog.text

def test_schema_validation_multiple_heads(caplog, mock_alembic_env):
    caplog.set_level(logging.INFO)
    mock_alembic_env['script'].get_heads.return_value = ["head1", "head2"]
    mock_alembic_env['context'].get_current_heads.return_value = ["head1", "head2"]
    
    # Should not raise exception
    check_alembic_head()
    assert "STARTUP STEP: APPLICATION READY" in caplog.text

def test_schema_validation_missing_version_table(caplog, mock_alembic_env):
    caplog.set_level(logging.INFO)
    mock_alembic_env['script'].get_heads.return_value = ["abcd1234efgh"]
    mock_alembic_env['context'].get_current_heads.return_value = []
    
    with pytest.raises(RuntimeError, match="SCHEMA VALIDATION FAILED"):
        check_alembic_head()

def test_schema_validation_corrupt_revision(caplog, mock_alembic_env):
    caplog.set_level(logging.INFO)
    mock_alembic_env['script'].get_heads.return_value = ["abcd1234efgh"]
    mock_alembic_env['context'].get_current_heads.return_value = ["corrupt1234"]
    
    with pytest.raises(RuntimeError, match="SCHEMA VALIDATION FAILED"):
        check_alembic_head()

def test_database_unavailable_retry_success(caplog, mock_alembic_env):
    caplog.set_level(logging.INFO)
    mock_alembic_env['script'].get_heads.return_value = ["abcd1234efgh"]
    mock_alembic_env['context'].get_current_heads.return_value = ["abcd1234efgh"]
    
    # Make engine.connect fail 3 times, then succeed
    mock_connection = mock_alembic_env['engine'].connect.return_value
    mock_alembic_env['engine'].connect.side_effect = [
        OperationalError("stmt", "params", "orig"),
        OperationalError("stmt", "params", "orig"),
        OperationalError("stmt", "params", "orig"),
        mock_connection
    ]
    
    check_alembic_head()
    
    assert "Database unavailable, retrying" in caplog.text
    assert "STARTUP STEP: APPLICATION READY" in caplog.text

def test_database_unavailable_fatal(caplog, mock_alembic_env):
    caplog.set_level(logging.INFO)
    
    # Make engine.connect fail completely
    mock_alembic_env['engine'].connect.side_effect = OperationalError("stmt", "params", "orig")
    
    with pytest.raises(OperationalError):
        check_alembic_head()
        
    assert "Database unavailable after 5 attempts" in caplog.text
