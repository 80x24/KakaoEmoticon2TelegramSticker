import datetime

from io import BytesIO
from typing import List

from PIL import Image
from aiohttp import ClientError, ClientSession
from telegram import Update, InputSticker
from telegram.constants import StickerFormat
from telegram.ext import ContextTypes

from config import EMOTICON_ID_REGEX
from converter import is_animated_webp, webp_to_webm


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Your user ID: {update.effective_user.id}",
    )


async def create_emoticon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user:
        return

    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="URL을 입력해주세요.",
        )
        return

    emoticon_url = context.args[0]

    if not EMOTICON_ID_REGEX.match(emoticon_url):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="유효한 이모티콘 URL이 아닙니다.",
        )

        return

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="이모티콘 정보를 불러오는 중입니다.",
    )

    emoticon_url = emoticon_url.replace(
        "https://e.kakao.com/t/",
        "https://e.kakao.com/api/items/",
    )

    async with ClientSession() as session:
        try:
            async with session.get(emoticon_url) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except ClientError:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="이모티콘 정보를 가져올 수 없습니다.",
            )
            return

        items = data["contents"]["items"]
        if not items:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="이모티콘 목록이 비어 있습니다.",
            )
            return

        title = data["hero"]["title"]

        first_anim_bytes = b""
        if first_anim_url := items[0].get("animatedUrl"):
            async with session.get(first_anim_url) as r:
                first_anim_bytes = await r.read()
        is_animated = is_animated_webp(first_anim_bytes)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"{title} 이모티콘을 다운로드 합니다. "
                 f"({'동영상' if is_animated else '정적'} 스티커, {len(items)}개)",
        )

        stickers: List[InputSticker] = []

        if is_animated:
            for idx, item in enumerate(items):
                if idx == 0:
                    webp_data = first_anim_bytes
                else:
                    async with session.get(item["animatedUrl"]) as r:
                        webp_data = await r.read()
                webm = await webp_to_webm(webp_data)
                stickers.append(
                    InputSticker(
                        sticker=webm,
                        emoji_list=["😀"],
                        format=StickerFormat.VIDEO,
                    )
                )
        else:
            for item in items:
                async with session.get(item["thumbnailUrl"]) as img:
                    img_bytes = BytesIO()
                    Image.open(BytesIO(await img.read())).resize((512, 512)).save(
                        img_bytes, "png"
                    )
                    stickers.append(
                        InputSticker(
                            sticker=img_bytes.getvalue(),
                            emoji_list=["😀"],
                            format=StickerFormat.STATIC,
                        )
                    )
    cur_time = str(datetime.datetime.now(datetime.timezone.utc).timestamp()).replace(".", "")
    sticker_name = f"t{cur_time}_by_{context.bot.name[1:]}"

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"총 {len(stickers)}개의 이모티콘을 텔레그램 서버로 업로드합니다.",
    )

    doing_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"업로드 중... (0/{len(stickers)})",
    )

    await context.bot.create_new_sticker_set(
        user_id=update.effective_user.id,
        name=sticker_name,
        title=title,
        stickers=[stickers[0]],
    )

    await doing_message.edit_text(
        text=f"업로드 중... (1/{len(stickers)})",
    )

    for index, sticker in enumerate(stickers[1:], 2):
        await context.bot.add_sticker_to_set(
            user_id=update.effective_user.id,
            name=sticker_name,
            sticker=sticker,
        )
        await doing_message.edit_text(
            text=f"업로드 중... ({index}/{len(stickers)})",
        )

    await doing_message.edit_text(
        text=f"{title} 스티커 생성이 완료되었습니다!",
    )

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"https://t.me/addstickers/{sticker_name}",
    )