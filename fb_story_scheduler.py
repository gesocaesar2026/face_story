#!/usr/bin/env python3
"""
fb_story_scheduler.py

وظيفة:
- يطلب من Google Gemini (GenAI) رسالة قصيرة + برومبت صورة.
- يطلب من Gemini توليد صورة (موديل صورة).
- يكتب الرسالة على الصورة (مقاس ستوري، 1080x1920)، ثم يرفعها وينشرها كـ Story على صفحة فيسبوك.

متطلبات env / GitHub Secrets:
- FB_TOKEN  -> توكن صفحة فيسبوك (Secret)
- PAGE_ID   -> رقم صفحة الفيسبوك (Secret)
- GEMINI_API_KEY -> مفتاح Google AI (Secret)
- FONT_PATH (اختياري) -> ./fonts/ad.ttf
- OUTPUT_DIR (اختياري) -> ./output
"""
import os
import sys
import json
import time
import base64
import uuid
import requests
from datetime import datetime
from textwrap import wrap
from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color

# Google GenAI SDK
try:
    from google import genai
    from google.genai import types
except Exception as e:
    genai = None
    types = None

# ---- إعدادات (من متغيرات البيئة لملاءمة GitHub Actions) ----
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FB_ACCESS_TOKEN = os.environ.get("FB_TOKEN")
PAGE_ID = os.environ.get("PAGE_ID")
FONT_PATH = os.environ.get("FONT_PATH", "./fonts/ad.ttf")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "./output")
LOG_FILE = os.environ.get("LOG_FILE", "./output/action_log.txt")

os.makedirs(OUTPUT_DIR, exist_ok=True)

session = requests.Session()

def fatal(msg):
    print(f"[FATAL] {msg}")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} - FATAL - {msg}\n")
    sys.exit(1)

# تحقق من المتغيرات المطلوبة قبل الاستمرار
if not FB_ACCESS_TOKEN:
    fatal("FB_TOKEN غير معرف. اضبطه كـ GitHub Secret.")
if not PAGE_ID:
    fatal("PAGE_ID غير معرف. اضبطه كـ GitHub Secret.")
if not GEMINI_API_KEY:
    fatal("GEMINI_API_KEY غير معرف. اضبطه كـ GitHub Secret.")
if not os.path.exists(FONT_PATH):
    fatal(f"ملف الخط غير موجود: {FONT_PATH}")

# --- تهيئة عميل Gemini (Google GenAI SDK) ---
if genai is None:
    fatal("مكتبة google-genai غير مثبتة. أضفها في requirements.txt")

client = genai.Client(api_key=GEMINI_API_KEY)

# --- دوال مساعدة ---
def log_message(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} - {msg}\n")

# اطلب من Gemini رسالة قصيرة + برومبت للصورة بصيغة JSON
def ask_gemini_for_message_and_prompt(style_hint="short, comforting, Christian tone"):
    """
    يطلب من Gemini أن يرجع JSON بالشكل:
    {"message": "رسالة قصيرة بالعربية", "image_prompt": "english prompt for image generation"}
    """
    system_instruction = (
        "You are an assistant that creates short comforting Christian messages in Arabic "
        "and companion English image prompts. "
        "Return ONLY valid JSON with two keys: 'message' and 'image_prompt'. "
        "The 'message' should be short (max ~120 characters) in Arabic. "
        "The 'image_prompt' should be an English prompt, detailed enough to generate a warm, comforting religious image, "
        "avoid modern brand names or celebrities. Keep the tone positive and hopeful."
    )
    user_instruction = (
        f"Generate one message + image prompt. Style hint: {style_hint}.\n\n"
        "Output JSON example:\n"
        '{"message":"...","image_prompt":"..."}'
    )

    contents = system_instruction + "\n\n" + user_instruction

    # نطلب نفس الاستجابة أن تحتوي على TEXT + IMAGE لو أردنا أن Gemini يولد الصورة مباشرة
    # ولكن هنا نستخدمه أولاً لإرجاع النص والبرومبت.
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["Text"])
        )
    except Exception as e:
        log_message(f"خطأ أثناء استدعاء Gemini للحصول على message/prompt: {e}")
        return None, None

    text = getattr(resp, "text", None) or getattr(resp, "content", None) or str(resp)
    # حاول استخراج JSON من النص
    try:
        # قد يرسل Gemini خرائط أو نصوص — نحاول إيجاد قوس JSON أول/آخر
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_text = text[start:end+1]
            data = json.loads(json_text)
            return data.get("message"), data.get("image_prompt")
        else:
            # كحل احتياطي: إذا كان النموذج يرجع "message: ... \n image_prompt: ..."
            lines = text.splitlines()
            msg = None
            prompt = None
            for line in lines:
                if line.lower().startswith("message"):
                    msg = line.split(":",1)[1].strip().strip('"')
                if line.lower().startswith("image_prompt"):
                    prompt = line.split(":",1)[1].strip().strip('"')
            return msg, prompt
    except Exception as e:
        log_message(f"فشل تحليل JSON من Gemini: {e} -- النص المستلم: {text}")
        return None, None

# اطلب من Gemini توليد الصورة فعليًا (موديل صورة) واحفظها
def generate_image_via_gemini(image_prompt, out_path):
    """
    يستخدم موديل الصورة (gemini-2.5-flash-image أو imagen) لإرجاع صورة.
    سينتج الصورة ويكتبها كـ PNG في out_path.
    """
    # استخدم موديل صورة مناسب؛ ممكن تغييره حسب توافر الموديلات في حسابك
    model_name = "gemini-2.5-flash-image"
    contents = image_prompt

    try:
        resp = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["Image","Text"])
        )
    except Exception as e:
        log_message(f"خطأ أثناء طلب توليد الصورة من Gemini: {e}")
        return False

    # محاولة استخراج الصورة من الاستجابة
    # المخرجات المتوقعة: resp قد يحتوي على حقل .image_blocks أو .images أو .candidates مع بيانات base64
    # سنجرب عدة طرق آمنة للقراءة:
    try:
        # بعض نسخ SDK توفر resp.image or resp.images
        if hasattr(resp, "images") and resp.images:
            img_bytes = resp.images[0].content  # قد تكون بايتس مباشرة
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            return True

        # أحيانًا تكون الصورة داخل resp.output[0].image[0].b64 или candidate
        # حاول كشف أي سلسلة base64 في النص
        text_repr = getattr(resp, "text", "") or str(resp)
        # ابحث عن بلوك base64 png/jpg
        b64_index = text_repr.find("data:image")
        if b64_index != -1:
            # expected: data:image/png;base64,....
            comma = text_repr.find(",", b64_index)
            b64 = text_repr[comma+1:].strip()
            b = base64.b64decode(b64)
            with open(out_path, "wb") as f:
                f.write(b)
            return True

        # آخر محاولة: تفحص كل السمات في resp.__dict__ وابحث عن بايتات أو سلاسل base64
        resp_dict = resp.__dict__ if hasattr(resp, "__dict__") else {}
        def find_b64_in(obj):
            if isinstance(obj, dict):
                for k,v in obj.items():
                    r = find_b64_in(v)
                    if r:
                        return r
            elif isinstance(obj, list):
                for it in obj:
                    r = find_b64_in(it)
                    if r:
                        return r
            elif isinstance(obj, (bytes, bytearray)):
                # مفترض أن تكون بايتس كاملة
                return obj
            elif isinstance(obj, str):
                if obj.strip().startswith("/9j/") or obj.strip().startswith("iVBOR"):  # jpg/png base64 starts
                    return base64.b64decode(obj.strip())
            return None

        b_data = find_b64_in(resp_dict)
        if b_data:
            with open(out_path, "wb") as f:
                f.write(b_data)
            return True

    except Exception as e:
        log_message(f"خطأ أثناء استخراج الصورة من استجابة Gemini: {e}")

    log_message("لم أعثر على صورة في استجابة Gemini.")
    return False

# ضبط الصورة لمقاس Story وكتابة النص
def prepare_and_write_text(image_path, message, out_path, target_w=1080, target_h=1920):
    # resize/crop to 9:16 and add text center
    with Image(filename=image_path) as img:
        img.transform(resize=f"{target_w}x{target_h}^")
        img.crop(width=target_w, height=target_h, gravity='center')
        img.background_color = Color('white')

        with Drawing() as draw:
            draw.font = FONT_PATH
            draw.font_size = 64
            draw.fill_color = Color('white')
            draw.stroke_color = Color('black')
            draw.stroke_width = 2

            lines = wrap(message, width=20)
            line_height = 80
            rect_height = line_height * len(lines)
            rect_width = 0
            for line in lines:
                metrics = draw.get_font_metrics(img, line)
                if metrics.text_width > rect_width:
                    rect_width = metrics.text_width

            rect_x1 = (img.width - rect_width) / 2 - 20
            rect_y1 = (img.height / 2) - (rect_height / 2) - 10

            # background box
            draw.fill_color = Color('black')
            draw.fill_opacity = 0.5
            draw.rectangle(left=int(rect_x1), top=int(rect_y1), width=int(rect_width)+40, height=int(rect_height)+30)
            draw(img)

            # write text white
            draw.fill_color = Color('white')
            draw.stroke_width = 0
            y_text = int(rect_y1) + line_height - 20
            for line in lines:
                text_width = draw.get_font_metrics(img, line).text_width
                x_text = int((img.width - text_width) / 2)
                draw.text(x_text, y_text, line)
                y_text += line_height
            draw(img)

        img.save(filename=out_path)
    return out_path

# رفع الصورة كـ photo (published=false) ثم إنشاء Story
def upload_photo_get_id(image_path):
    with open(image_path, "rb") as img_file:
        payload = {"published": "false", "access_token": FB_ACCESS_TOKEN}
        files = {"source": img_file}
        resp = session.post(f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos", data=payload, files=files, timeout=180)
    try:
        return resp.json().get("id"), resp.json()
    except Exception:
        return None, {"error": "invalid json", "status_code": resp.status_code}

def publish_story_from_photo(photo_id, caption=""):
    payload = {"photo_id": photo_id, "access_token": FB_ACCESS_TOKEN}
    if caption:
        payload["message"] = caption
    resp = session.post(f"https://graph.facebook.com/v19.0/{PAGE_ID}/photo_stories", data=payload, timeout=60)
    try:
        return resp.json()
    except Exception:
        return {"error": "invalid json", "status_code": resp.status_code}

# === التشغيل الرئيسي: حلقة مفردة (من الأفضل أن يقوم الـ Action بتشغيله كل نصف ساعة) ===
def run_once():
    log_message("Start: طلب رسالة + برومبت من Gemini")
    message, image_prompt = ask_gemini_for_message_and_prompt()
    if not message or not image_prompt:
        log_message("لم يتم الحصول على message أو image_prompt من Gemini. إيقاف المحاولة.")
        return

    log_message(f"Gemini returned message (len {len(message)}): {message}")
    log_message(f"Gemini returned image_prompt: {image_prompt}")

    temp_img = os.path.join(OUTPUT_DIR, f"raw_{uuid.uuid4().hex[:8]}.png")
    final_img = os.path.join(OUTPUT_DIR, f"story_{uuid.uuid4().hex[:8]}.png")

    # توليد الصورة
    ok = generate_image_via_gemini(image_prompt, temp_img)
    if not ok:
        log_message("فشل توليد الصورة عبر Gemini.")
        return

    # كتابة النص على الصورة (مقاس ستوري)
    prepare_and_write_text(temp_img, message, final_img)

    # رفع الصورة ثم إنشاء ستوري
    photo_id, raw = upload_photo_get_id(final_img)
    if not photo_id:
        log_message(f"فشل رفع الصورة: {json.dumps(raw, ensure_ascii=False)}")
    else:
        log_message(f"تم رفع الصورة photo_id={photo_id} - الآن إنشاء ستوري...")
        res = publish_story_from_photo(photo_id, caption=message)
        log_message(f"نتيجة إنشاء الستوري: {json.dumps(res, ensure_ascii=False)}")

    # تنظيف
    for p in (temp_img, final_img):
        try:
            os.remove(p)
        except Exception:
            pass

if __name__ == "__main__":
    # هذا السكربت مفروض يعمل مرة واحدة عند استدعاء الـ Action.
    # حاولت تصميمه بهذه الطريقة لأن GitHub Actions سيشغله كل نصف ساعة طبق الـ cron.
    run_once()
