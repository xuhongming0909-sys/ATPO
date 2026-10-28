# AI-SUMMARY: 全局 GUI 锁测试——同一时刻只允许一个自动化任务进入同花顺操作区
import pytest

from shared.errors import AutoIpoError
from shared.gui_lock import gui_lock


def test_second_gui_operation_is_rejected_while_lock_is_held():
    with gui_lock("first"):
        with pytest.raises(AutoIpoError) as exc:
            with gui_lock("second", timeout_s=0.1):
                pass
    assert exc.value.code == "GUI_LOCK_BUSY"
    assert "first" in str(exc.value.context)
