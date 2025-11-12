#!/usr/bin/env python3
import os
import requests
import uuid
import time
from datetime import datetime
from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color
from textwrap import wrap
import sys
import json

# ===== إعدادات عبر متغيرات البيئة (مناسب للـ GitHub Actions) =====
FONT_PATH = os.environ.get("FONT_PATH", "./fonts/ad.ttf")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "./output")
PAGE_ID = os.environ.get("PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_TOKEN")

os.makedirs(OUTPUT_DIR, exist_ok=True)

LOG_FILE = os.environ.get("LOG_FILE", "log.txt")
session = requests.Session()

# === تحقق سريع من المتغيرات اللازمة ===
def fatal(msg):
    print(f"[FATAL] {msg}")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} - FATAL - {msg}\n")
    sys.exit(1)

if not PAGE_ID:
    fatal("PAGE_ID غير موجود. ضبطه كـ Secret باسم PAGE_ID.")
if not FB_ACCESS_TOKEN:
    fatal("FB_TOKEN غير موجود. ضبطه كـ Secret باسم FB_TOKEN.")
if not os.path.exists(FONT_PATH):
    fatal(f"ملف الخط غير موجود في المسار: {FONT_PATH}. أضف الخط داخل ./fonts/ad.ttf أو عدّل FONT_PATH.")

# --- المحتوى (قوائم جاهزة) ---
messages_short = [
    "أنا جنبك في كل لحظة، ماتخليش حاجة توقفك.",
    "قوتي في ضعفك، وأنا معاك طول الطريق.",
    "بحبك بلا حدود، وأنا ملجأك في كل ضيق.",
    "خليك واثق، أنا دايمًا هأديك سلام القلب.",
    "ارفع إيدك ليّا، هشيل عنك كل تعب.",
    "أنا النور اللي بيهدّي دربك مهما كان مظلم.",
    "صوت قلبي بيناديك، تعال وخد سلامي.",
    "معايا، مفيش حاجة تخليك تخاف أو تحزن.",
    "أنا الراعي اللي بيسير معاك مهما تعبت.",
    "أنا راحة القلب في وسط العواصف.",
    "أحضان المحبة مفتوحة ليك دايمًا.",
    "ما تخليش الهم يسرق فرحتك، أنا معاك.",
    "أنا السلام اللي بيعمر قلبك من جديد.",
    "خليك قريب مني، وهتلاقي الفرح الحقيقي.",
    "أنا سندك لما الدنيا تتعاند معاك.",
    "هدفي أخليك دايمًا واقف ومتفائل.",
    "تعالى ليّ في كل وقت، هتلاقي الراحة.",
    "أنا سبب فرحتك رغم كل الظروف.",
    "ما تسيبش شكوكك توقفك، أنا معاك.",
    "أنا محبة ما بتنتهي، وأنا ليك وحدك.",
    "أنا صوت السلام اللي بيدخل قلبك.",
    "أنا دايمًا جنبك، حتى في أحلك الأيام.",
    "بحبك من كل قلبي، وما هسيبكش.",
    "أنا نورك لما الدنيا تتلبد بالسواد.",
]

image_prompts = [
    "Jesus Christ embracing a soul with radiant light, calm spiritual background, hopeful Christian art",
    "Jesus standing with open arms in a glowing sunrise, inviting peace and love, religious imagery",
    "Jesus as the Good Shepherd protecting his flock on green hills, peaceful Christian symbolism",
    "Jesus comforting a tired person with soft light, compassionate and healing scene",
    "Jesus shining as a bright beacon in dark clouds, symbol of hope and faith",
    "Jesus wiping tears from a person’s face, warm glow, spiritual comfort art",
    "Jesus walking beside a lonely soul on a shining path, heavenly light and peace",
    "Jesus removing burdens with glowing hands, symbol of relief and divine help",
    "Jesus empowering a fragile heart with celestial light, spiritual encouragement",
    "Jesus victorious over darkness with radiant crown, symbolizing faith triumph",
    "Jesus sheltering a person under his wings, protective light and care",
    "Jesus bringing peace to a troubled heart, serene and calm spiritual imagery",
    "Jesus as a loyal friend, strong loving presence in a comforting Christian scene",
    "Jesus' mercy pouring like water with cleansing light, symbolizing hope and forgiveness",
    "Jesus standing firm like a rock with shining background, symbol of strength and steadfastness",
    "Jesus shining light on a dark path, guiding lost souls to hope and peace",
    "Jesus holding a glowing heart symbolizing unconditional love and healing",
    "Jesus surrounded by heavenly light walking through clouds, spiritual journey theme",
    "Jesus comforting a child with gentle light in a peaceful garden, Christian art",
    "Jesus leading sheep through green pastures under warm sunlight, pastoral Christian imagery",
    "Jesus offering a hand to a fallen person, radiant and encouraging Christian scene",
    "Jesus' love enveloping a broken soul with warm golden light, healing theme",
    "Jesus standing tall with arms raised, radiant glory, symbol of divine victory",
    "Jesus lighting a candle in darkness, symbolizing hope and faith renewal",
]

# --- Helpers ---
def log_message(message):
    print(message)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} - {message}\n")

def download_image(prompt, retries=3):
    url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            content_type = resp.headers.get("Content-Type", "")
            if "image" in content_type:
                img_path = os.path.join(OUTPUT_DIR, f"temp_{uuid.uuid4().hex[:8]}.png")
                with open(img_path, "wb") as f:
                    f.write(resp.content)
                return img_path
            else:
                log_message(f"لم يتم استلام صورة (نوع المحتوى: {content_type}). محاولة {attempt+1}/{retries}")
        except Exception as e:
            log_message(f"خطأ أثناء تحميل الصورة: {e}. محاولة {attempt+1}/{retries}")
    raise Exception("فشل تحميل الصورة بعد عدة محاولات.")

# Resize/crop to 9:16 story size (1080x1920)
def prepare_for_story(image_path, out_path, target_w=1080, target_h=1920):
    with Image(filename=image_path) as img:
        img.transform(resize=f"{target_w}x{target_h}^")
        img.crop(width=target_w, height=target_h, gravity='center')
        img.background_color = Color('white')
        img.save(filename=out_path)
    return out_path

def add_text_to_image(image_path, phrase):
    temp_story = os.path.join(OUTPUT_DIR, f"story_{uuid.uuid4().hex[:8]}.png")
    prepare_for_story(image_path, temp_story)
    final_path = os.path.join(OUTPUT_DIR, f"final_{uuid.uuid4().hex[:8]}.png")
    with Image(filename=temp_story) as img:
        width, height = img.width, img.height
        with Drawing() as draw:
            draw.font = FONT_PATH
            draw.font_size = 60
            draw.fill_color = Color('red')
            draw.stroke_color = Color('black')
            draw.stroke_width = 2
            lines = wrap(phrase, width=24)
            line_height = 70
            rect_height = line_height * len(lines)
            rect_width = 0
            for line in lines:
                metrics = draw.get_font_metrics(img, line)
                if metrics.text_width > rect_width:
                    rect_width = metrics.text_width
            rect_x1 = (width - rect_width) / 2 - 10
            rect_y1 = (height / 2) - (rect_height / 2) - 10
            draw.fill_color = Color('white')
            draw.fill_opacity = 0.7
            draw.stroke_width = 0
            draw.rectangle(left=int(rect_x1), top=int(rect_y1), width=int(rect_width)+20, height=int(rect_height)+20)
            draw.fill_color = Color('red')
            draw.stroke_color = Color('black')
            draw.stroke_width = 2
            y_text = int(rect_y1) + line_height - 10
            for line in lines:
                text_width = draw.get_font_metrics(img, line).text_width
                x_text = int((width - text_width) / 2)
                draw.text(x_text, y_text, line)
                y_text += line_height
            draw(img)
        # footer
        with Drawing() as footer_draw:
            footer_draw.font = FONT_PATH
            footer_draw.font_size = 28
            footer_draw.fill_color = Color('white')
            footer_metrics = footer_draw.get_font_metrics(img, "لا تنسى الاشتراك في صفحتنا #رسالة_من_ابوك_السماوي")
            footer_height = int(footer_metrics.text_height + 20)
            footer_y = height - footer_height
            with img.clone() as footer_img:
                footer_draw.fill_color = Color('black')
                footer_draw.rectangle(left=0, top=footer_y, width=width, height=footer_height)
                footer_draw(footer_img)
                footer_draw.fill_color = Color('white')
                footer_draw.text(int((width - footer_metrics.text_width) / 2), footer_y + int(footer_metrics.text_height), "لا تنسى الاشتراك في صفحتنا #رسالة_من_ابوك_السماوي")
                footer_draw(footer_img)
                img.sequence[0] = footer_img
        img.save(filename=final_path)
    try:
        os.remove(temp_story)
    except Exception:
        pass
    return final_path

# === Facebook upload: upload photo (published=false) ثم إنشاء story مباشرة ===
def upload_photo_get_id(image_path):
    with open(image_path, "rb") as img_file:
        payload = {"published": "false", "access_token": FB_ACCESS_TOKEN}
        files = {"source": img_file}
        resp = session.post(f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos", data=payload, files=files, timeout=180)
    try:
        result = resp.json()
    except Exception:
        result = {"error": "invalid json response", "status_code": resp.status_code}
    return result.get("id"), result

def publish_story_from_photo(photo_id, caption=""):
    payload = {"photo_id": photo_id, "access_token": FB_ACCESS_TOKEN}
    if caption:
        payload["message"] = caption
    resp = session.post(f"https://graph.facebook.com/v19.0/{PAGE_ID}/photo_stories", data=payload, timeout=60)
    try:
        return resp.json()
    except Exception:
        return {"error": "invalid json response", "status_code": resp.status_code}

def main():
    total = min(len(messages_short), len(image_prompts))
    log_message(f"بدء نشر {total} ستوري مباشرةً.")
    for i in range(total):
        phrase = messages_short[i]
        prompt = image_prompts[i]
        log_message(f"[{i+1}/{total}] جلب صورة للستوري...")
        try:
            img_path = download_image(prompt)
        except Exception as e:
            log_message(f"فشل في جلب الصورة: {e}")
            continue
        try:
            final_img = add_text_to_image(img_path, phrase)
        except Exception as e:
            log_message(f"فشل معالجة الصورة: {e}")
            try:
                os.remove(img_path)
            except Exception:
                pass
            continue
        photo_id, raw = upload_photo_get_id(final_img)
        if not photo_id:
            log_message(f"فشل رفع الصورة: {json.dumps(raw, ensure_ascii=False)}")
        else:
            log_message(f"تم رفع الصورة photo_id={photo_id} - الآن إنشاء ستوري...")
            res = publish_story_from_photo(photo_id, caption=phrase)
            log_message(f"نتيجة إنشاء الستوري: {json.dumps(res, ensure_ascii=False)}")
        # تنظيف مؤقت
        for p in (img_path, final_img):
            try:
                os.remove(p)
            except Exception:
                pass
        time.sleep(3)  # تخفيف ضغط على الـ API
    log_message("انتهت المحاولة.")

if __name__ == "__main__":
    main()
