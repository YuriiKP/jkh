from aiogram import F, filters
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message
from filters import IsMainAdmin
from loader import bot, dp


####ДЛЯ ОПРЕДЕЛЕНИЯ ID МЕДИАФАЙЛА НА СЕРВЕРЕ ТГ####
####################################################
@dp.message(filters.Command("det"), IsMainAdmin())
async def detect_file_id(message: Message, state: FSMContext):
    if message.photo:
        print(message.photo[-1].file_id)
        await message.answer(text=f"file_id = {message.photo[-1].file_id}\n\n")

    if message.video:
        if message.video.width == message.video.height:
            video = (await bot.download(file=message.video)).read()
            video_note = await message.answer_video_note(
                video_note=BufferedInputFile(file=video, filename="video_note")
            )
            text = f"vodeo file_id = {message.video.file_id}\n\nvideo_note file_id = {video_note.video_note.file_id}"

        else:
            text = f"vodeo file_id = {message.video.file_id}"

        await message.answer(text=text)

    if message.document:
        print(message.document.file_id)
        await message.answer(text=f"file_id = {message.document.file_id}\n\n")


####################################################
