import pytest

from src.poster import (
    ComposerNotFoundError,
    GroupNotFoundError,
    PublishError,
    ResultStatus,
    UploadTimeoutError,
    create_post,
    detect_result,
    open_group,
    publish,
    upload_images,
)
from tests.fakes import FakePage


async def test_open_group_navigates_to_url():
    page = FakePage()
    await open_group(page, "https://facebook.com/groups/1")
    assert page.goto_calls == ["https://facebook.com/groups/1"]


async def test_open_group_timeout_raises_group_not_found():
    page = FakePage()
    page.should_goto_timeout = True
    with pytest.raises(GroupNotFoundError):
        await open_group(page, "https://facebook.com/groups/1")


async def test_create_post_clicks_trigger_and_fills_content():
    page = FakePage()
    await create_post(page, "Hello world")
    trigger = page._get("role:button:Create post")
    textbox = page._get("role:textbox:None")
    assert trigger.clicked is True
    assert textbox.filled_text == "Hello world"


async def test_create_post_missing_trigger_raises_composer_not_found():
    page = FakePage()
    page.configure("role:button:Create post", should_timeout=True)
    with pytest.raises(ComposerNotFoundError):
        await create_post(page, "Hello world")


async def test_create_post_missing_textbox_raises_composer_not_found():
    page = FakePage()
    page.configure("role:textbox:None", should_timeout=True)
    with pytest.raises(ComposerNotFoundError):
        await create_post(page, "Hello world")


async def test_upload_images_empty_list_is_noop():
    page = FakePage()
    await upload_images(page, [])
    assert "css:input[type='file']" not in page._locators


async def test_upload_images_success_sets_files():
    page = FakePage()
    await upload_images(page, ["a.jpg", "b.jpg"])
    file_input = page._get("css:input[type='file']")
    assert file_input.uploaded_files == ["a.jpg", "b.jpg"]


async def test_upload_images_timeout_raises_upload_timeout_error():
    page = FakePage()
    page.configure("css:input[type='file']", should_timeout=True)
    with pytest.raises(UploadTimeoutError):
        await upload_images(page, ["a.jpg"])


async def test_publish_clicks_publish_button():
    page = FakePage()
    await publish(page)
    btn = page._get("role:button:Post")
    assert btn.clicked is True


async def test_publish_timeout_raises_publish_error():
    page = FakePage()
    page.configure("role:button:Post", should_timeout=True)
    with pytest.raises(PublishError):
        await publish(page)


async def test_detect_result_dialog_open_returns_failed():
    page = FakePage()
    page.configure("role:dialog:None", should_timeout=True)
    status = await detect_result(page, "Hello world")
    assert status == ResultStatus.FAILED


async def test_detect_result_stuck_publish_button_returns_failed():
    page = FakePage()
    page.configure("role:button:Post", visible=True)
    status = await detect_result(page, "Hello world")
    assert status == ResultStatus.FAILED


async def test_detect_result_dialog_closed_no_verify_returns_unknown():
    page = FakePage()
    page.configure("role:button:Post", visible=False)
    status = await detect_result(page, "Hello world", verify_feed=False)
    assert status == ResultStatus.UNKNOWN


async def test_detect_result_verify_feed_found_returns_success():
    page = FakePage()
    page.configure("role:button:Post", visible=False)
    page.configure("text:Hello world", visible=True)
    status = await detect_result(page, "Hello world", verify_feed=True)
    assert status == ResultStatus.SUCCESS


async def test_detect_result_verify_feed_not_found_returns_unknown():
    page = FakePage()
    page.configure("role:button:Post", visible=False)
    page.configure("text:Hello world", visible=False)
    status = await detect_result(page, "Hello world", verify_feed=True)
    assert status == ResultStatus.UNKNOWN
