"""UI text for Zyraena's popup, in English (default) and Turkish."""

import os

DEFAULT_LANGUAGE = "en"

STRINGS = {
    "en": {
        "greeting": "*looks down at you* {user}... Zyraena is listening. What do you need?",
        "pet_menu_chat": "Open chat",
        "pet_menu_talk": "Say something",
        "pet_menu_hide": "Hide",
        "window_title": "Zyraena",
        "send_button": "Send",
        "lang_toggle": "TR",
        "credits_loading": "Tavily: loading...",
        "credits_unknown": "Tavily credits: unknown",
        "credits_failed": "Failed to fetch Tavily credits",
        "credits_format": "Tavily: {remaining}/{limit} credits",
        "web_search_failed": "Web search failed: {error}",
        "web_search_no_results": "No results found for that web search.",
        "memory_no_keywords": "Couldn't find any meaningful keywords to search for.",
        "memory_no_matches": "I couldn't find anything about that in past conversations.",
        "unknown_tool": "Unknown tool: {name}",
        "tool_error": "Tool execution error: {error}",
        "too_many_tool_calls": "Too many tool calls were made, I couldn't produce an answer.",
        "connection_error": "Couldn't connect to {provider}. Could you try again in a bit?",
        "invalid_api_key": "{provider} API key is invalid or missing. Check {env} in the .env file.",
        "model_not_found": "{provider} doesn't recognize the model '{model}' (it may be retired). Set a current model in the .env file.",
        "rate_limited": "Rate limit reached. Could you try again in a bit?",
        "server_overloaded": "{provider}'s servers are overloaded right now (tried a few times). Could you try again in a bit?",
        "mode_switched": "Switched to {mode} mode ({model}). We'll continue this conversation there.",
        "mode_current": "Current mode: {mode} ({model}). Available: {modes}. Switch with /mode <name>.",
        "mode_unknown": "There's no '{mode}' mode. Available: {modes}.",
        "generic_error": "Error: {error}",
        "avatar_load_failed": "Failed to load avatar ({filename}): {error}",
        "voice_not_ready": "Voice feature isn't active yet (getting ready for speech-to-text/text-to-speech).",
        "confirm_title": "Zyraena needs your permission",
        "confirm_create_folder": "Shall I create this folder?\n\n{path}",
        "confirm_write_file": "Shall I create this file? ({chars} characters)\n\n{path}",
        "confirm_overwrite_file": "This file already exists. Shall I overwrite it? ({chars} characters)\n\n{path}",
        "confirm_move": "Shall I move this?\n\n{source}\n→\n{destination}",
        "confirm_organize": "Shall I sort {count} files in {folder} into subfolders? Nothing is deleted.\n\n{plan}",
        "confirm_whatsapp_send": "Send this on WhatsApp?\n\n📎 {file}\n→ {to}\n\nCheck that the chat and the file are right.",
        "confirm_whatsapp_chats": "Shall I look at your chat list in WhatsApp Desktop?",
        "confirm_whatsapp_read": "Shall I read the last {count} messages of the chat open in WhatsApp Desktop?",
        "confirm_whatsapp_chat": "Open this chat in WhatsApp Desktop and read its last {count} messages?\n\n💬 {chat}\n\nIts new messages will show as read.",
        "confirm_web_tabs": "Shall I look at your open Opera GX tabs?",
        "confirm_web_open": "Open this in a new Opera GX tab?\n\n🌐 {url}",
        "confirm_web_close": "Close this Opera GX tab?\n\n🗂 {title}\n{url}",
        "confirm_web_switch": "Bring this Opera GX tab to the front?\n\n🗂 {title}\n{url}",
        "confirm_web_read": "Shall I read this page?\n\n🗂 {title}\n{url}",
        "confirm_web_click": "Click this in Opera GX?\n\n👆 {target}\n🗂 {title}",
        "confirm_web_type": "Type this in Opera GX?\n\n⌨️ {text}\n→ {target}\n🗂 {title}",
        "confirm_web_type_submit": "Type this in Opera GX and submit it?\n\n⌨️ {text}\n→ {target}\n🗂 {title}",
        "confirm_web_download": "Download this?\n\n⬇️ {what}\n🗂 {title}",
        "confirm_web_upload": "Upload this file to the site?\n\n📎 {file} ({size})\n→ {target}\n🗂 {title}\n{url}",
        "answered_on_pc": "✔️ Answered on the PC: {answer}",
        "confirm_sleep_mode": "Start sleep mode?\n\nJob: {task}\n\nFolders:\n{folders}\n\nBackup first (~{size} MB) into:\n{failsafe}\n\nAfter this I won't ask anything: I'll finish the job on my own, send the report on Telegram and shut the PC down.",
        "sleep_report_title": "# 🌙 Sleep mode report",
        "sleep_report_task": "**Job:** {task}",
        "sleep_report_time": "**Time:** {start} → {end}",
        "sleep_report_done": "**Result:** ✅ Done.",
        "sleep_report_not_done": "**Result:** ⚠️ Not finished (see the explanation below).",
        "sleep_report_changes": "## Changed folders",
        "sleep_report_backup": "Before-copy: {backup}",
        "sleep_report_added": "**Added ({count}):**",
        "sleep_report_changed": "**Changed ({count}):**",
        "sleep_report_deleted": "**Deleted ({count}):**",
        "sleep_report_no_changes": "No file was changed.",
        "sleep_report_claude": "## What was done and why",
        "sleep_cli_shutdown_comment": "Zyraena sleep mode: the job is done, the PC shuts down in 60 seconds. To stop it: /iptal on Telegram or shutdown /a",
        "sleep_cli_shutdown_ok": "⏻ The PC shuts down in 60 seconds (checked: Windows has it planned). To stop it: /iptal on Telegram (while Zyraena runs) or `shutdown /a` on the PC.",
        "sleep_cli_shutdown_failed": "⚠️ The PC could NOT be shut down: {error}. It is still on.",
        "sleep_cli_report_cut": "(The full report is attached.)",
        "sleep_full_backup_no_space": "⚠️ **Backup:** not enough disk space for the full backup ({need} GB needed, {free} GB free), so only the job's folders were copied first; other project folders were copied before their first change only when a tool call named them.",
        "sleep_full_backup_failed": "⚠️ **Backup:** these couldn't be copied at the start (they were copied again before any change, or the change was blocked): {folders}",
        "health_gpu_temp": "GPU temperature {value:.0f}°C (limit {limit:.0f}°C)",
        "health_ram": "RAM {value:.0f}% full (limit {limit:.0f}%)",
        "health_cpu": "CPU load {value:.0f}% (limit {limit:.0f}%)",
        "health_disk": "Disk {drive} has only {value:.1f}% free (limit {limit:.0f}%)",
        "health_alert": "⚠️ Health alarm: {what}.\nUsing it most: {culprit}\n\nIf there's no answer within {minutes} minutes and it's still like this, I'll end it.",
        "health_alert_report": "⚠️ Health alarm: {what}.\nEnding a program won't free space; some files need to go.",
        "health_unknown_culprit": "(couldn't tell)",
        "health_button_end": "🛑 End it",
        "health_button_keep": "✅ Leave it",
        "health_reminder": "⏰ Still: {what}. If there's no answer, I'll end it in {minutes} min.",
        "health_recovered": "✅ Back to normal ({what}); I didn't touch anything.",
        "health_kept": "OK, I'm leaving it alone. I won't warn about this again for {minutes} minutes.",
        "health_nothing_to_end": "Still: {what}, but there's no program I'm allowed to end for it.",
        "health_reason_asked": "you said so",
        "health_reason_timeout": "no answer for {minutes} minutes",
        "health_ended": "🛑 Ended {culprit} ({reason}).",
        "health_end_failed": "Couldn't end {culprit}: {error}",
        "health_after": "Now: {what}.",
        "confirm_delete": "Shall I send this to the Recycle Bin?\n\n{path}",
        "confirm_open": "Shall I open this?\n\n{path}",
        "confirm_launch": "Shall I launch {name}?",
        "confirm_yes": "✅ Yes",
        "confirm_no": "❌ No",
        "telegram_new_chat": "Fresh start. I've forgotten our last conversation (and Claude Code's too).",
        "claude_usage": "Write what Claude Code should do after /c, e.g. /c add a new button to Zyraena",
        "claude_forwarding": "Passing it to Claude Code. This can take a few minutes; I'll write when it's done.",
        "claude_done": "Claude Code finished:\n\n{answer}",
        "claude_failed": "Claude Code couldn't do it:\n\n{answer}",
        "confirm_close_app": "Shall I close {app}?\n\n{titles}",
        "confirm_force_close_app": "Force-close {app}? Unsaved work in it will be lost.",
        "confirm_end_process": "End this process? Unsaved work in it will be lost.\n\n{process}\nChild processes: {children}",
        "confirm_run_python": "Shall I run this Python file?\n\n{path} {args}",
        "confirm_stop_run": "Shall I stop run #{run_id} ({name})?",
        "confirm_uninstall_game": "Uninstall {name}? ({size})\n\n{folder}\n\nThis is permanent (it doesn't go to the Recycle Bin). Steam will close and reopen.",
        "openrouter_credits": "💳 OpenRouter credit left: ${remaining:.2f}",
        "openrouter_estimate": "≈ {messages} more messages at the recent average (${average:.4f} per message, last {count} messages).",
        "openrouter_credits_failed": "Couldn't read the OpenRouter credit balance.",
        "alarm_remote": "⏰ {name}",
        "screenshot_caption": "📸 Screen",
        "voice_confirm": "🎤 This is what I understood:\n\n“{text}”\n\nShall I do it?",
        "voice_declined": "Okay, I won't do it. Say it again (or type it) and I'll try once more.",
        "voice_not_understood": "I couldn't make out your voice message. Could you try again?",
        "voice_reply_failed": "Couldn't make the voice reply: {error}",
        "box_hint": "Write to Zyraena… (Enter sends, Esc closes)",
        "box_thinking": "Zyraena is thinking",
        "panel_title": "Zyraena",
        "panel_openrouter": "OpenRouter credit",
        "panel_tavily": "Tavily credit",
        "panel_loading": "loading…",
        "panel_failed": "couldn't be read",
        "panel_unknown": "unknown",
        "panel_tavily_value": "{remaining} / {limit}",
        "panel_pet_hide": "Hide the pet",
        "panel_pet_show": "Show the pet",
        "panel_hint": "Esc or Ctrl+F1 closes",
        "web_ext_missing_dir": "The Zyraena Web Control extension's folder {folder} is missing (moved or deleted).",
        "web_ext_not_loaded": "The Zyraena Web Control extension isn't loaded in Opera GX. Load it once: "
                              "opera://extensions > Developer mode > Load unpacked > {folder}.",
        "web_ext_gone": "Opera GX still loads the Zyraena Web Control extension from {path}, which doesn't exist any "
                        "more. In opera://extensions remove it and Load unpacked {folder}.",
        "web_ext_other_path": "Opera GX loads the Zyraena Web Control extension from {path}, not from {folder}, so "
                              "changes there don't reach it. Remove it in opera://extensions and Load unpacked {folder}.",
        "web_ext_old": "Opera GX runs an old copy of the Zyraena Web Control extension (version {version}, {wanted} "
                       "needed). Press the reload button on its card in opera://extensions.",
        "web_ext_not_connected": "Opera GX is open but the Zyraena Web Control extension hasn't connected for over "
                                 "{minutes} minutes. Check it's switched on in opera://extensions.",
        "web_ext_dead_others": "Opera GX has extensions whose folders don't exist any more ({paths}); they do "
                               "nothing. Remove them in opera://extensions.",
        "confirm_yes": "Yes",
        "confirm_no": "No",
        "voice_off_game": "A game is running, so I'm not speaking: the reply stays as text.",
        "voice_off_busy": "Something else keeps the GPU busy, so I'm not speaking: the reply stays as text.",
        "voice_off_slow": "My voice got too slow (is the GPU busy?), the rest stays as text. I'll try speaking again in 10 minutes.",
        "voice_off_off": "Spoken replies are turned off (ZYRAENA_TTS=off).",
        "voice_off_missing": "The local voice isn't set up (tts_env or its model is missing), so the reply stays as text.",
        "mic_listening": "🎙 Listening… press ⏹ when you're done.",
        "mic_failed": "Microphone problem: {error}",
        "sample_right": "✓ right",
        "sample_fix": "✎ fix",
        "sample_saved": "kept for voice training",
        "sample_failed": "couldn't keep it: {error}",
        "sample_fix_title": "Fix the transcript",
        "sample_fix_prompt": "What did you actually say?",
        "power_q_shutdown": "Shall I shut down the PC?",
        "power_q_restart": "Shall I restart the PC?",
        "power_when_now": "When: now (with a 1-minute warning first).",
        "power_when_at": "When: {time} (in {minutes} min).",
        "power_when_run": "When: after run #{run_id} ({name}) finishes.",
        "power_force_note": "Unsaved work in open apps will be lost.",
        "power_warning_shutdown": "⏻ The PC shuts down in 60 seconds. To stop it, tell me to cancel (on Telegram: /iptal).",
        "power_warning_restart": "🔄 The PC restarts in 60 seconds. To stop it, tell me to cancel (on Telegram: /iptal).",
        "power_cancelled": "Shutdown cancelled, the PC stays on.",
        "power_nothing_planned": "No shutdown was planned.",
        "run_finished": "✅ Run #{run_id} {name} finished ({duration}, exit code {code}).\n\nLast output:\n{tail}",
        "run_failed": "❌ Run #{run_id} {name} failed ({duration}, exit code {code}).\n\nLast output:\n{tail}",
    },
    "tr": {
        "greeting": "*başını eğerek sana bakar* {user}... Zyraena seni dinliyor. Ne istiyorsun?",
        "pet_menu_chat": "Sohbeti aç",
        "pet_menu_talk": "Bir şey söyle",
        "pet_menu_hide": "Gizle",
        "window_title": "Zyraena",
        "send_button": "Gönder",
        "lang_toggle": "EN",
        "credits_loading": "Tavily: yükleniyor...",
        "credits_unknown": "Tavily kredisi: bilinmiyor",
        "credits_failed": "Tavily kredisi alınamadı",
        "credits_format": "Tavily: {remaining}/{limit} kredi",
        "web_search_failed": "Web araması başarısız oldu: {error}",
        "web_search_no_results": "Web aramasında sonuç bulunamadı.",
        "memory_no_keywords": "Aranacak anlamlı bir kelime bulunamadı.",
        "memory_no_matches": "Geçmiş konuşmalarda buna dair bir şey bulamadım.",
        "unknown_tool": "Bilinmeyen araç: {name}",
        "tool_error": "Araç çalıştırma hatası: {error}",
        "too_many_tool_calls": "Çok fazla araç çağrısı yapıldı, bir cevap üretemedim.",
        "connection_error": "{provider} servisine bağlanılamadı. Birazdan tekrar dener misin?",
        "invalid_api_key": "{provider} API anahtarı geçersiz veya eksik. .env dosyasındaki {env} değerini kontrol et.",
        "model_not_found": "{provider} '{model}' modelini tanımıyor (emekliye ayrılmış olabilir). .env dosyasında güncel bir model ayarla.",
        "rate_limited": "İstek limiti doldu (rate limit). Birazdan tekrar dener misin?",
        "server_overloaded": "{provider} sunucuları şu an aşırı yüklü (birkaç kez denedim). Birazdan tekrar dener misin?",
        "mode_switched": "{mode} moduna geçtim ({model}). Konuşmaya buradan devam ediyoruz.",
        "mode_current": "Şu anki mod: {mode} ({model}). Seçenekler: {modes}. Değiştirmek için /mode <isim>.",
        "mode_unknown": "'{mode}' diye bir mod yok. Seçenekler: {modes}.",
        "generic_error": "Hata: {error}",
        "avatar_load_failed": "Avatar yüklenemedi ({filename}): {error}",
        "voice_not_ready": "Ses özelliği henüz aktif değil (speech-to-text/text-to-speech için hazırlık).",
        "confirm_title": "Zyraena izin istiyor",
        "confirm_create_folder": "Bu klasörü oluşturayım mı?\n\n{path}",
        "confirm_write_file": "Bu dosyayı oluşturayım mı? ({chars} karakter)\n\n{path}",
        "confirm_overwrite_file": "Bu dosya zaten var. Üzerine yazayım mı? ({chars} karakter)\n\n{path}",
        "confirm_move": "Bunu taşıyayım mı?\n\n{source}\n→\n{destination}",
        "confirm_organize": "{folder} içindeki {count} dosyayı alt klasörlere ayırayım mı? Hiçbir şey silinmez.\n\n{plan}",
        "confirm_whatsapp_send": "WhatsApp'tan gönderilsin mi?\n\n📎 {file}\n→ {to}\n\nSohbetin ve dosyanın doğru olduğunu kontrol et.",
        "confirm_whatsapp_chats": "WhatsApp Desktop'taki sohbet listene bakayım mı?",
        "confirm_whatsapp_read": "WhatsApp Desktop'ta açık sohbetin son {count} mesajını okuyayım mı?",
        "confirm_whatsapp_chat": "WhatsApp Desktop'ta bu sohbeti açıp son {count} mesajını okuyayım mı?\n\n💬 {chat}\n\nYeni mesajları okundu görünecek.",
        "confirm_web_tabs": "Opera GX'te açık sekmelerine bakayım mı?",
        "confirm_web_open": "Opera GX'te yeni sekmede açayım mı?\n\n🌐 {url}",
        "confirm_web_close": "Bu Opera GX sekmesini kapatayım mı?\n\n🗂 {title}\n{url}",
        "confirm_web_switch": "Bu Opera GX sekmesine geçeyim mi?\n\n🗂 {title}\n{url}",
        "confirm_web_read": "Bu sayfayı okuyayım mı?\n\n🗂 {title}\n{url}",
        "confirm_web_click": "Opera GX'te buna tıklayayım mı?\n\n👆 {target}\n🗂 {title}",
        "confirm_web_type": "Opera GX'te bunu yazayım mı?\n\n⌨️ {text}\n→ {target}\n🗂 {title}",
        "confirm_web_type_submit": "Opera GX'te bunu yazıp göndereyim mi?\n\n⌨️ {text}\n→ {target}\n🗂 {title}",
        "confirm_web_download": "Bunu indireyim mi?\n\n⬇️ {what}\n🗂 {title}",
        "confirm_web_upload": "Bu dosyayı siteye yükleyeyim mi?\n\n📎 {file} ({size})\n→ {target}\n🗂 {title}\n{url}",
        "answered_on_pc": "✔️ PC'den cevaplandı: {answer}",
        "confirm_sleep_mode": "Uyku modu başlasın mı?\n\nGörev: {task}\n\nKlasörler:\n{folders}\n\nÖnce yedek (~{size} MB):\n{failsafe}\n\nBundan sonra hiçbir şey sormayacağım: işi kendim bitirip raporu Telegram'dan atacağım ve PC'yi kapatacağım.",
        "sleep_report_title": "# 🌙 Uyku modu raporu",
        "sleep_report_task": "**Görev:** {task}",
        "sleep_report_time": "**Zaman:** {start} → {end}",
        "sleep_report_done": "**Sonuç:** ✅ Tamamlandı.",
        "sleep_report_not_done": "**Sonuç:** ⚠️ Bitmedi (açıklaması aşağıda).",
        "sleep_report_changes": "## Değişen klasörler",
        "sleep_report_backup": "Önceki hali: {backup}",
        "sleep_report_added": "**Eklenen ({count}):**",
        "sleep_report_changed": "**Değişen ({count}):**",
        "sleep_report_deleted": "**Silinen ({count}):**",
        "sleep_report_no_changes": "Hiçbir dosya değişmedi.",
        "sleep_report_claude": "## Ne yapıldı ve neden",
        "sleep_cli_shutdown_comment": "Zyraena uyku modu: is bitti, PC 60 saniye icinde kapaniyor. Durdurmak icin: Telegram'da /iptal ya da shutdown /a",
        "sleep_cli_shutdown_ok": "⏻ PC 60 saniye içinde kapanıyor (kontrol ettim: Windows kapatmayı planladı). Durdurmak için: Telegram'da /iptal (Zyraena açıksa) ya da PC'de `shutdown /a`.",
        "sleep_cli_shutdown_failed": "⚠️ PC kapatılAMADI: {error}. Hâlâ açık.",
        "sleep_cli_report_cut": "(Raporun tamamı ekte.)",
        "sleep_full_backup_no_space": "⚠️ **Yedek:** tam yedeğe disk yetmedi ({need} GB lazım, {free} GB boş). Bu yüzden önce sadece işin klasörleri kopyalandı; diğer proje klasörleri ancak bir komut onları adıyla andığında, ilk değişiklikten önce kopyalandı.",
        "sleep_full_backup_failed": "⚠️ **Yedek:** bunlar başta kopyalanamadı (değişiklikten önce tekrar kopyalandı ya da değişiklik engellendi): {folders}",
        "health_gpu_temp": "GPU sıcaklığı {value:.0f}°C (sınır {limit:.0f}°C)",
        "health_ram": "RAM %{value:.0f} dolu (sınır %{limit:.0f})",
        "health_cpu": "CPU yükü %{value:.0f} (sınır %{limit:.0f})",
        "health_disk": "{drive} diskinde sadece %{value:.1f} boş yer var (sınır %{limit:.0f})",
        "health_alert": "⚠️ Sağlık alarmı: {what}.\nEn çok kullanan: {culprit}\n\n{minutes} dakika içinde cevap gelmezse ve durum düzelmezse onu kapatacağım.",
        "health_alert_report": "⚠️ Sağlık alarmı: {what}.\nProgram kapatmak yer açmaz, bazı dosyaların silinmesi gerek.",
        "health_unknown_culprit": "(tespit edemedim)",
        "health_button_end": "🛑 Kapat",
        "health_button_keep": "✅ Dokunma",
        "health_reminder": "⏰ Hâlâ: {what}. Cevap gelmezse {minutes} dakika sonra kapatacağım.",
        "health_recovered": "✅ Normale döndü ({what}), hiçbir şeye dokunmadım.",
        "health_kept": "Tamam, dokunmuyorum. {minutes} dakika boyunca bunun için tekrar uyarmayacağım.",
        "health_nothing_to_end": "Hâlâ: {what}, ama kapatmama izin verilen bir program yok.",
        "health_reason_asked": "sen istedin",
        "health_reason_timeout": "{minutes} dakikadır cevap yok",
        "health_ended": "🛑 {culprit} kapatıldı ({reason}).",
        "health_end_failed": "{culprit} kapatılamadı: {error}",
        "health_after": "Şimdi: {what}.",
        "confirm_delete": "Bunu Geri Dönüşüm Kutusu'na göndereyim mi?\n\n{path}",
        "confirm_open": "Bunu açayım mı?\n\n{path}",
        "confirm_launch": "{name} başlatılsın mı?",
        "confirm_yes": "✅ Evet",
        "confirm_no": "❌ Hayır",
        "telegram_new_chat": "Sayfayı temizledim. Önceki konuşmamızı (ve Claude Code'unkini) unuttum.",
        "claude_usage": "/c'den sonra Claude Code'un ne yapacağını yaz, ör. /c Zyraena'ya yeni bir buton ekle",
        "claude_forwarding": "Claude Code'a iletiyorum. Birkaç dakika sürebilir, bitince yazarım.",
        "claude_done": "Claude Code bitirdi:\n\n{answer}",
        "claude_failed": "Claude Code bunu yapamadı:\n\n{answer}",
        "confirm_close_app": "{app} kapatılsın mı?\n\n{titles}",
        "confirm_force_close_app": "{app} zorla kapatılsın mı? İçindeki kaydedilmemiş işler kaybolur.",
        "confirm_end_process": "Bu işlem sonlandırılsın mı? İçindeki kaydedilmemiş işler kaybolur.\n\n{process}\nAlt işlem sayısı: {children}",
        "confirm_run_python": "Bu Python dosyasını çalıştırayım mı?\n\n{path} {args}",
        "confirm_stop_run": "#{run_id} ({name}) durdurulsun mu?",
        "confirm_uninstall_game": "{name} silinsin mi? ({size})\n\n{folder}\n\nSilme kalıcı, Geri Dönüşüm Kutusu'na gitmez. Steam kapanıp yeniden açılacak.",
        "openrouter_credits": "💳 Kalan OpenRouter kredisi: ${remaining:.2f}",
        "openrouter_estimate": "≈ {messages} mesaj daha yeter (son {count} mesajın ortalaması: mesaj başına ${average:.4f}).",
        "openrouter_credits_failed": "OpenRouter kredisi okunamadı.",
        "alarm_remote": "⏰ {name}",
        "screenshot_caption": "📸 Ekran",
        "voice_confirm": "🎤 Şunu anladım:\n\n“{text}”\n\nBunu yapayım mı?",
        "voice_declined": "Tamam, yapmıyorum. Tekrar söyle ya da yaz, yeniden deneyeyim.",
        "voice_not_understood": "Sesli mesajını anlayamadım, tekrar dener misin?",
        "voice_reply_failed": "Sesli cevabı hazırlayamadım: {error}",
        "box_hint": "Zyraena'ya yaz… (Enter gönderir, Esc kapatır)",
        "box_thinking": "Zyraena düşünüyor",
        "panel_title": "Zyraena",
        "panel_openrouter": "OpenRouter kredisi",
        "panel_tavily": "Tavily kredisi",
        "panel_loading": "yükleniyor…",
        "panel_failed": "alınamadı",
        "panel_unknown": "bilinmiyor",
        "panel_tavily_value": "{remaining} / {limit}",
        "panel_pet_hide": "Pet'i gizle",
        "panel_pet_show": "Pet'i göster",
        "panel_hint": "Esc ya da Ctrl+F1 kapatır",
        "web_ext_missing_dir": "Zyraena Web Control eklentisinin klasörü {folder} yok (taşınmış ya da silinmiş).",
        "web_ext_not_loaded": "Zyraena Web Control eklentisi Opera GX'te yüklü değil. Bir kez yükle: "
                              "opera://extensions > Geliştirici modu > Paketlenmemiş öğe yükle > {folder}.",
        "web_ext_gone": "Opera GX, Zyraena Web Control eklentisini hâlâ {path} klasöründen yüklüyor ama o klasör artık "
                        "yok. opera://extensions'ta onu kaldır ve {folder} klasörünü yükle.",
        "web_ext_other_path": "Opera GX, Zyraena Web Control eklentisini {folder} yerine {path} klasöründen yüklüyor; "
                              "{folder} içindeki değişiklikler ona ulaşmıyor. opera://extensions'ta kaldırıp {folder} "
                              "klasörünü yükle.",
        "web_ext_old": "Opera GX, Zyraena Web Control eklentisinin eski bir kopyasını çalıştırıyor (sürüm {version}, "
                       "{wanted} gerekli). opera://extensions'ta kartındaki yenile düğmesine bas.",
        "web_ext_not_connected": "Opera GX açık ama Zyraena Web Control eklentisi {minutes} dakikadan uzun süredir "
                                 "bağlanmadı. opera://extensions'ta açık olduğuna bak.",
        "web_ext_dead_others": "Opera GX'te klasörü artık olmayan eklentiler var ({paths}); hiçbir şey yapmıyorlar. "
                               "opera://extensions'ta kaldır.",
        "confirm_yes": "Evet",
        "confirm_no": "Hayır",
        "voice_off_game": "Oyun açık, o yüzden sesli cevap vermiyorum: cevap yazıda.",
        "voice_off_busy": "GPU'yu başka bir şey meşgul ediyor, sesli cevap vermiyorum: cevap yazıda.",
        "voice_off_slow": "Sesim çok yavaşladı (GPU meşgul mü?), kalanı yazıda. 10 dakika sonra tekrar sesli denerim.",
        "voice_off_off": "Sesli cevap kapalı (ZYRAENA_TTS=off).",
        "voice_off_missing": "Yerel ses kurulu değil (tts_env ya da modeli eksik), cevap yazıda.",
        "mic_listening": "🎙 Dinliyorum… bitince ⏹'a bas.",
        "mic_failed": "Mikrofon sorunu: {error}",
        "sample_right": "✓ doğru",
        "sample_fix": "✎ düzelt",
        "sample_saved": "ses eğitimi için kaydedildi",
        "sample_failed": "kaydedilemedi: {error}",
        "sample_fix_title": "Metni düzelt",
        "sample_fix_prompt": "Aslında ne dedin?",
        "power_q_shutdown": "PC'yi kapatayım mı?",
        "power_q_restart": "PC'yi yeniden başlatayım mı?",
        "power_when_now": "Ne zaman: şimdi (önce 1 dakika uyarı veririm).",
        "power_when_at": "Ne zaman: {time} ({minutes} dk sonra).",
        "power_when_run": "Ne zaman: #{run_id} ({name}) bitince.",
        "power_force_note": "Açık uygulamalardaki kaydedilmemiş işler kaybolur.",
        "power_warning_shutdown": "⏻ PC 60 saniye içinde kapanıyor. Durdurmak için bana iptal et de (Telegram'da: /iptal).",
        "power_warning_restart": "🔄 PC 60 saniye içinde yeniden başlıyor. Durdurmak için bana iptal et de (Telegram'da: /iptal).",
        "power_cancelled": "Kapatma iptal edildi, PC açık kalıyor.",
        "power_nothing_planned": "Planlanmış bir kapatma yoktu.",
        "run_finished": "✅ #{run_id} {name} bitti ({duration}, çıkış kodu {code}).\n\nSon çıktı:\n{tail}",
        "run_failed": "❌ #{run_id} {name} hata ile bitti ({duration}, çıkış kodu {code}).\n\nSon çıktı:\n{tail}",
    },
}

# The API credit log (credit_log) and the panel's Credits tab.
STRINGS["en"].update({
    "panel_credit_log": "API credit log",
    "panel_tab_credits": "Credits",
    "credits_pending": "waiting…",
    "credits_source_box": "Text box",
    "credits_source_telegram": "Telegram",
    "credits_source_voice": "Voice chat",
    "credits_source_stt": "Speech-to-text (cloud)",
    "credits_source_disk": "Disk scan",
    "credits_source_other": "Other",
    "credits_tools": "tools",
    "credits_round": "{n}. {model} · {prompt} in + {completion} out tokens · {cost}",
    "credits_total": "Reported cost {cost} · balance {before} → {after} (difference {difference})",
    "credits_tavily": "Tavily: {searches} searches · credit {before} → {after} ({used} used)",
    "credits_overlap_note": "* Another request ran at the same time: the balance difference includes it too.",
    "credits_mismatch_note": "The balance difference doesn't match the reported cost: OpenRouter may lower the "
                             "balance late, or something else uses the same key.",
    "credits_no_before_note": "No balance from before: it couldn't be read, or the request started outside the log.",
    "credits_period_today": "Today",
    "credits_period_week": "Last 7 days",
    "credits_period_month": "Last 30 days",
    "credits_period_all": "All",
    "credits_all_sources": "All sources",
    "credits_hint": "Select a row for the details · * = overlapping requests",
    "credits_col_time": "Time",
    "credits_col_source": "Source",
    "credits_col_what": "What for",
    "credits_col_model": "Model",
    "credits_col_requests": "Req.",
    "credits_col_cost": "Cost",
    "credits_col_before": "Before",
    "credits_col_after": "After",
    "credits_col_difference": "Difference",
    "credits_select": "Select an entry to see each request in it.",
    "credits_summary_part": "{period}: {cost} ({count})",
    "credits_empty": "No paid requests in this period yet.",
})
STRINGS["tr"].update({
    "panel_credit_log": "API kredi kaydı",
    "panel_tab_credits": "Krediler",
    "credits_pending": "bekleniyor…",
    "credits_source_box": "Yazı kutusu",
    "credits_source_telegram": "Telegram",
    "credits_source_voice": "Sesli sohbet",
    "credits_source_stt": "Ses tanıma (bulut)",
    "credits_source_disk": "Disk taraması",
    "credits_source_other": "Diğer",
    "credits_tools": "araçlar",
    "credits_round": "{n}. {model} · {prompt} giriş + {completion} çıkış token · {cost}",
    "credits_total": "Bildirilen maliyet {cost} · bakiye {before} → {after} (fark {difference})",
    "credits_tavily": "Tavily: {searches} arama · kredi {before} → {after} ({used} harcandı)",
    "credits_overlap_note": "* Aynı anda başka bir istek de vardı: bakiye farkı onu da içeriyor.",
    "credits_mismatch_note": "Bakiye farkı bildirilen maliyetle tutmuyor: OpenRouter bakiyeyi geç düşürmüş olabilir "
                             "ya da aynı anahtarı başka bir şey kullanıyor.",
    "credits_no_before_note": "Önceki bakiye yok: okunamadı ya da istek kayıt başlamadan yapıldı.",
    "credits_period_today": "Bugün",
    "credits_period_week": "Son 7 gün",
    "credits_period_month": "Son 30 gün",
    "credits_period_all": "Hepsi",
    "credits_all_sources": "Tüm kaynaklar",
    "credits_hint": "Ayrıntı için bir satır seç · * = aynı anda olan istekler",
    "credits_col_time": "Zaman",
    "credits_col_source": "Kaynak",
    "credits_col_what": "Ne için",
    "credits_col_model": "Model",
    "credits_col_requests": "İstek",
    "credits_col_cost": "Maliyet",
    "credits_col_before": "Önce",
    "credits_col_after": "Sonra",
    "credits_col_difference": "Fark",
    "credits_select": "İçindeki istekleri görmek için bir kayıt seç.",
    "credits_summary_part": "{period}: {cost} ({count})",
    "credits_empty": "Bu dönemde henüz ücretli istek yok.",
})

# The disk scanner (disk_tools) and the panel's Disk tab.
STRINGS["en"].update({
    "panel_tab_general": "General",
    "panel_tab_disk": "Disk",
    "disk_name_recycle": "Recycle Bin",
    "disk_name_voice": "Zyraena's voice (environments, models)",
    "disk_name_mei_own": "_MEI folder of the running Zyraena",
    "disk_name_mei": "_MEI leftovers ({count} folders)",
    "disk_name_loose": "{folder} (loose files)",
    "disk_name_root": "Files in the root of C:",
    "disk_name_steam_common": "Steam leftover: {name}",
    "disk_name_steam_workshop": "Steam Workshop leftover: {name}",
    "disk_what_root": "Windows' paging / hibernation files: {files}. `powercfg /h off` (admin) removes hiberfil.sys "
                      "if you never hibernate",
    "disk_what_steam_common": "A game folder in Steam's library that no installed game owns (left by an uninstall: "
                              "mods, saves, configs)",
    "disk_what_steam_workshop": "Workshop downloads of a game that isn't installed",
    "disk_name_steam_depot": "Steam depot download: {name}",
    "disk_what_steam_depot": "Game files fetched with the Steam console's download_depot (e.g. to downgrade); not "
                             "needed once copied into the game's folder",
    "disk_protect_root": "Windows manages these files",
    "disk_cache_pip": "pip cache",
    "disk_cache_uv": "uv cache",
    "disk_cache_torch": "torch cache",
    "disk_cache_npm": "npm cache",
    "disk_cache_dxcache": "NVIDIA DXCache",
    "disk_cache_crashdumps": "Crash dumps",
    "disk_cache_vscode_crashpad": "VS Code Crashpad",
    "disk_cache_vscode_vsix": "VS Code CachedExtensionVSIXs",
    "disk_cache_vortex_downloads": "Vortex downloads",
    "disk_cache_temp": "Temp",
    "disk_cache_hf": "HuggingFace hub (other)",
    "disk_progress_start": "Scanning the drive…",
    "disk_progress": "Scanning: {dirs} folders, {gb:.0f} GB so far…",
    "disk_what_venv": "Python {python} environment, {count} packages ({notable})",
    "disk_what_project": "Project folder (code you wrote)",
    "disk_what_game": "Steam game",
    "disk_what_model": "HuggingFace model, downloaded again when needed",
    "disk_what_mei": "Folders PyInstaller exes left in Temp when they were closed by force",
    "disk_what_mei_own": "Files of the Zyraena that is running now",
    "disk_what_python": "Base Python install (venvs are built on it)",
    "disk_what_own": "Your own files",
    "disk_what_system": "Part of Windows",
    "disk_what_app": "Zyraena's own files",
    "disk_what_loose": "Files lying directly in this folder (its sub-folders are listed apart)",
    "disk_what_link_shortcut": "Shortcut",
    "disk_what_link_startup": "Starts with Windows",
    "disk_what_link_task": "Scheduled task",
    "disk_what_cache_pip": "Downloaded Python wheels; pip downloads them again when needed",
    "disk_what_cache_uv": "uv's package cache; venvs made by uv may hard-link files from here",
    "disk_what_cache_torch": "torch hub downloads (model weights)",
    "disk_what_cache_npm": "Downloaded npm packages",
    "disk_what_cache_dxcache": "Compiled shaders; games rebuild them (the first start after deleting stutters)",
    "disk_what_cache_crashdumps": "Memory dumps of crashed programs",
    "disk_what_cache_vscode_crashpad": "VS Code's crash reports",
    "disk_what_cache_vscode_vsix": "Copies of VS Code extensions it already installed",
    "disk_what_cache_vortex_downloads": "Mod archives Vortex downloaded (installed mods are elsewhere)",
    "disk_what_cache_temp": "Temporary files",
    "disk_what_cache_hf": "Rest of the HuggingFace cache (locks, small files)",
    "disk_protect_windows": "Windows",
    "disk_protect_system": "part of Windows",
    "disk_protect_system_program": "a Windows component or driver (use Settings > Apps)",
    "disk_protect_steam_common": "Steam's shared installers",
    "disk_protect_container": "a folder holding other items: delete those instead",
    "disk_protect_link": "a shortcut: delete it where it is",
    "disk_protect_voice": "Zyraena's voice environments and models",
    "disk_protect_egitim": "Zyraena's voice environments are built on this venv",
    "disk_protect_failsafe": "sleep mode's backups",
    "disk_protect_own_mei": "the running Zyraena",
    "disk_protect_zyraena": "Zyraena herself",
    "disk_protect_pth": "{venv} uses this venv through a .pth file",
    "disk_protect_inside": "inside {name}, which is protected",
    "disk_kind_game": "Game",
    "disk_kind_program": "Program",
    "disk_kind_python": "Python",
    "disk_kind_venv": "Venv",
    "disk_kind_cache": "Cache",
    "disk_kind_model": "Model",
    "disk_kind_mei": "_MEI",
    "disk_kind_project": "Project",
    "disk_kind_own": "My files",
    "disk_kind_folder": "Folder",
    "disk_kind_system": "System",
    "disk_kind_app": "Zyraena",
    "disk_kind_link": "Shortcut",
    "disk_src_steam": "Steam",
    "disk_src_steam_never": "never played (Steam)",
    "disk_src_prefetch": "Prefetch",
    "disk_src_git": "last git commit",
    "disk_src_newest_file": "newest file",
    "disk_src_install_date": "install date",
    "disk_what_src_rule": "rule",
    "disk_what_src_exe": "exe info",
    "disk_what_src_gemini": "guess",
    "disk_what_src_owner": "owner",
    "disk_free_line": "{drive}  {free} free of {total}  ·  {used} used",
    "disk_scan_button": "Scan now",
    "disk_scanning": "Scanning…",
    "disk_never_scanned": "No scan yet. Press Scan now (the first one takes a few minutes).",
    "disk_last_scan": "Last scan {when} · {seconds:.0f} s · {items} items",
    "disk_col_kind": "Type",
    "disk_col_name": "Name",
    "disk_col_size": "Size",
    "disk_col_used": "Last used",
    "disk_col_what": "What it is",
    "disk_col_redl": "Re-downloadable",
    "disk_col_deps": "Dependencies",
    "disk_filter_all": "All types",
    "disk_filter_min": "at least",
    "disk_yes": "yes",
    "disk_no": "no",
    "disk_deps_needs": "needs {names}",
    "disk_deps_used_by": "{count} use it",
    "disk_deps_missing": "missing dependency: {path}",
    "disk_deps_same": "same packages as {names}",
    "disk_delete": "Delete…",
    "disk_protected": "Protected: {reason}",
    "disk_no_action": "No delete for this item",
    "disk_select": "Select an item",
    "disk_details_path": "Folder",
    "disk_timeline": "Disk use over time",
    "disk_timeline_total": "total used",
    "disk_growers": "Grew most this week",
    "disk_growers_none": "Not enough history yet (needs scans on different days).",
    "disk_confirm_title": "Delete {name}?",
    "disk_how_url": "Steam's uninstall opens (steam://uninstall/{appid}).",
    "disk_how_uninstaller": "The program's own uninstaller runs:\n{command}",
    "disk_how_command": "Its own clean-up command runs:\n{command}",
    "disk_how_delete": "Deleted for good (not to the Recycle Bin): {size}.",
    "disk_how_trash": "Moved to the Recycle Bin: {size}.",
    "disk_how_contents": "Files in it older than a day are deleted for good; files in use are skipped.",
    "disk_confirm_inside": "Goes with it:",
    "disk_confirm_breaks": "These break (missing dependency):",
    "disk_confirm_nothing": "Nothing else depends on it.",
    "disk_confirm_yes": "Delete",
    "disk_confirm_no": "Cancel",
    "disk_done": "Done: {name} ({freed} freed).",
    "disk_started": "Started: {name}. Finish it in its window, then scan again.",
    "disk_failed": "Didn't work: {error}",
    "disk_too_big_for_bin": "Doesn't fit in the Recycle Bin ({size}, {free} free there): Windows would delete it "
                            "for good, so nothing was done. Empty the bin first, or delete it in Explorer yourself.",
    "disk_not_in_bin": "{name} is gone but isn't in the Recycle Bin: Windows may have deleted it for good.",
    "disk_days_ago": "{days} days ago",
    "disk_today": "today",
    "disk_shared": "(+{size} hard-linked with another item)",
    "disk_guess_redl": "Re-downloadable (guess): {value}",
    "disk_deleting": "Working…",
    "disk_findings": "Disk: new findings",
    "disk_findings_title": "New findings",
    "disk_find_grew": "{name} grew by {size}",
    "disk_find_free": "Only {free} free (limit {limit})",
    "disk_find_stale": "{name}: {size}, unused for {days} days",
    "disk_find_mei": "{count} new _MEI folders in Temp",
    "disk_gemini_prompt": "For each folder or program below, say in at most 12 words of English what it is, and "
                          "whether deleting it loses nothing that can't be downloaded or installed again. Answer "
                          "only with JSON: a list of {{\"id\": number, \"what\": text, \"redownloadable\": true or "
                          "false}}.\n\n{items}",
})
STRINGS["tr"].update({
    "panel_tab_general": "Genel",
    "panel_tab_disk": "Disk",
    "disk_name_recycle": "Geri Dönüşüm Kutusu",
    "disk_name_voice": "Zyraena'nın sesi (ortamlar, modeller)",
    "disk_name_mei_own": "Çalışan Zyraena'nın _MEI klasörü",
    "disk_name_mei": "_MEI kalıntıları ({count} klasör)",
    "disk_name_loose": "{folder} (doğrudan içindeki dosyalar)",
    "disk_name_root": "C: kökündeki dosyalar",
    "disk_name_steam_common": "Steam kalıntısı: {name}",
    "disk_name_steam_workshop": "Steam Atölye kalıntısı: {name}",
    "disk_what_root": "Windows'un sayfa / hazırda bekletme dosyaları: {files}. Hiç hazırda bekletme kullanmıyorsan "
                      "`powercfg /h off` (yönetici) hiberfil.sys'i kaldırır",
    "disk_what_steam_common": "Steam kütüphanesinde hiçbir kurulu oyuna ait olmayan oyun klasörü (kaldırılan oyundan "
                              "kalmış: modlar, kayıtlar, ayarlar)",
    "disk_what_steam_workshop": "Kurulu olmayan bir oyunun Atölye indirmeleri",
    "disk_name_steam_depot": "Steam depot indirmesi: {name}",
    "disk_what_steam_depot": "Steam konsolunun download_depot komutuyla indirilmiş oyun dosyaları (ör. sürüm düşürmek "
                             "için); oyun klasörüne kopyalandıysa gereksiz",
    "disk_protect_root": "bu dosyaları Windows yönetir",
    "disk_cache_pip": "pip önbelleği",
    "disk_cache_uv": "uv önbelleği",
    "disk_cache_torch": "torch önbelleği",
    "disk_cache_npm": "npm önbelleği",
    "disk_cache_dxcache": "NVIDIA DXCache",
    "disk_cache_crashdumps": "Çökme dökümleri (CrashDumps)",
    "disk_cache_vscode_crashpad": "VS Code Crashpad",
    "disk_cache_vscode_vsix": "VS Code CachedExtensionVSIXs",
    "disk_cache_vortex_downloads": "Vortex indirmeleri",
    "disk_cache_temp": "Temp",
    "disk_cache_hf": "HuggingFace hub (diğer)",
    "disk_progress_start": "Disk taranıyor…",
    "disk_progress": "Taranıyor: {dirs} klasör, şimdiye kadar {gb:.0f} GB…",
    "disk_what_venv": "Python {python} ortamı, {count} paket ({notable})",
    "disk_what_project": "Proje klasörü (yazdığın kod)",
    "disk_what_game": "Steam oyunu",
    "disk_what_model": "HuggingFace modeli, gerekince yeniden indirilir",
    "disk_what_mei": "Zorla kapatılan PyInstaller exe'lerinin Temp'te bıraktığı klasörler",
    "disk_what_mei_own": "Şu an çalışan Zyraena'nın dosyaları",
    "disk_what_python": "Temel Python kurulumu (venv'ler bunun üstüne kurulur)",
    "disk_what_own": "Kendi dosyaların",
    "disk_what_system": "Windows'un parçası",
    "disk_what_app": "Zyraena'nın kendi dosyaları",
    "disk_what_loose": "Doğrudan bu klasörde duran dosyalar (alt klasörleri ayrı listelenir)",
    "disk_what_link_shortcut": "Kısayol",
    "disk_what_link_startup": "Windows'la başlar",
    "disk_what_link_task": "Zamanlanmış görev",
    "disk_what_cache_pip": "İndirilmiş Python paketleri; pip gerekince yeniden indirir",
    "disk_what_cache_uv": "uv'nin paket önbelleği; uv'nin kurduğu venv'ler buradan hardlink alabilir",
    "disk_what_cache_torch": "torch hub indirmeleri (model ağırlıkları)",
    "disk_what_cache_npm": "İndirilmiş npm paketleri",
    "disk_what_cache_dxcache": "Derlenmiş shader'lar; oyunlar yeniden üretir (silince ilk açılışta takılma olur)",
    "disk_what_cache_crashdumps": "Çöken programların bellek dökümleri",
    "disk_what_cache_vscode_crashpad": "VS Code'un çökme raporları",
    "disk_what_cache_vscode_vsix": "VS Code'un zaten kurduğu eklentilerin kopyaları",
    "disk_what_cache_vortex_downloads": "Vortex'in indirdiği mod arşivleri (kurulu modlar başka yerde)",
    "disk_what_cache_temp": "Geçici dosyalar",
    "disk_what_cache_hf": "HuggingFace önbelleğinin geri kalanı (kilitler, küçük dosyalar)",
    "disk_protect_windows": "Windows",
    "disk_protect_system": "Windows'un parçası",
    "disk_protect_system_program": "Windows bileşeni ya da sürücü (Ayarlar > Uygulamalar'dan)",
    "disk_protect_steam_common": "Steam'in ortak kurulum dosyaları",
    "disk_protect_container": "başka öğeleri tutan klasör: onları sil",
    "disk_protect_link": "kısayol: bulunduğu yerden sil",
    "disk_protect_voice": "Zyraena'nın ses ortamları ve modelleri",
    "disk_protect_egitim": "Zyraena'nın ses ortamları bu venv'in üstüne kurulu",
    "disk_protect_failsafe": "uyku modunun yedekleri",
    "disk_protect_own_mei": "çalışan Zyraena",
    "disk_protect_zyraena": "Zyraena'nın kendisi",
    "disk_protect_pth": "{venv} bu venv'i .pth dosyasıyla kullanıyor",
    "disk_protect_inside": "korunan {name} içinde",
    "disk_kind_game": "Oyun",
    "disk_kind_program": "Program",
    "disk_kind_python": "Python",
    "disk_kind_venv": "Venv",
    "disk_kind_cache": "Önbellek",
    "disk_kind_model": "Model",
    "disk_kind_mei": "_MEI",
    "disk_kind_project": "Proje",
    "disk_kind_own": "Dosyalarım",
    "disk_kind_folder": "Klasör",
    "disk_kind_system": "Sistem",
    "disk_kind_app": "Zyraena",
    "disk_kind_link": "Kısayol",
    "disk_src_steam": "Steam",
    "disk_src_steam_never": "hiç oynanmadı (Steam)",
    "disk_src_prefetch": "Prefetch",
    "disk_src_git": "son git commit",
    "disk_src_newest_file": "en yeni dosya",
    "disk_src_install_date": "kurulum tarihi",
    "disk_what_src_rule": "kural",
    "disk_what_src_exe": "exe bilgisi",
    "disk_what_src_gemini": "tahmin",
    "disk_what_src_owner": "sahip",
    "disk_free_line": "{drive}  {total} diskin {free} boş  ·  {used} dolu",
    "disk_scan_button": "Şimdi tara",
    "disk_scanning": "Taranıyor…",
    "disk_never_scanned": "Henüz tarama yok. Şimdi tara'ya bas (ilki birkaç dakika sürer).",
    "disk_last_scan": "Son tarama {when} · {seconds:.0f} sn · {items} öğe",
    "disk_col_kind": "Tür",
    "disk_col_name": "Ad",
    "disk_col_size": "Boyut",
    "disk_col_used": "Son kullanım",
    "disk_col_what": "Ne olduğu",
    "disk_col_redl": "Yeniden indirilir",
    "disk_col_deps": "Bağımlılıklar",
    "disk_filter_all": "Tüm türler",
    "disk_filter_min": "en az",
    "disk_yes": "evet",
    "disk_no": "hayır",
    "disk_deps_needs": "gerekli: {names}",
    "disk_deps_used_by": "{count} öğe kullanıyor",
    "disk_deps_missing": "bağımlılık yok: {path}",
    "disk_deps_same": "aynı paketler: {names}",
    "disk_delete": "Sil…",
    "disk_protected": "Korunuyor: {reason}",
    "disk_no_action": "Bu öğe için silme yok",
    "disk_select": "Bir öğe seç",
    "disk_details_path": "Klasör",
    "disk_timeline": "Zaman içinde doluluk",
    "disk_timeline_total": "toplam dolu",
    "disk_growers": "Bu hafta en çok büyüyenler",
    "disk_growers_none": "Henüz yeterli geçmiş yok (farklı günlerde tarama gerekiyor).",
    "disk_confirm_title": "{name} silinsin mi?",
    "disk_how_url": "Steam'in kaldırma penceresi açılır (steam://uninstall/{appid}).",
    "disk_how_uninstaller": "Programın kendi kaldırıcısı çalışır:\n{command}",
    "disk_how_command": "Kendi temizleme komutu çalışır:\n{command}",
    "disk_how_delete": "Kalıcı olarak silinir (Geri Dönüşüm Kutusu'na gitmez): {size}.",
    "disk_how_trash": "Geri Dönüşüm Kutusu'na taşınır: {size}.",
    "disk_how_contents": "İçindeki bir günden eski dosyalar kalıcı silinir; kullanımda olanlar atlanır.",
    "disk_confirm_inside": "Birlikte gidenler:",
    "disk_confirm_breaks": "Bunlar bozulur (bağımlılık yok olur):",
    "disk_confirm_nothing": "Başka hiçbir şey buna bağlı değil.",
    "disk_confirm_yes": "Sil",
    "disk_confirm_no": "Vazgeç",
    "disk_done": "Tamam: {name} ({freed} boşaldı).",
    "disk_started": "Başlatıldı: {name}. Penceresinde bitir, sonra tekrar tara.",
    "disk_failed": "Olmadı: {error}",
    "disk_too_big_for_bin": "Geri Dönüşüm Kutusu'na sığmıyor ({size}, kutuda {free} boş): Windows kalıcı silerdi, "
                            "hiçbir şey yapılmadı. Önce kutuyu boşalt ya da Gezgin'den kendin sil.",
    "disk_not_in_bin": "{name} silindi ama Geri Dönüşüm Kutusu'nda bulunamadı: Windows kalıcı silmiş olabilir.",
    "disk_days_ago": "{days} gün önce",
    "disk_today": "bugün",
    "disk_shared": "(+{size} başka öğeyle hardlink)",
    "disk_guess_redl": "Yeniden indirilebilir (tahmin): {value}",
    "disk_deleting": "Yapılıyor…",
    "disk_findings": "Disk: yeni bulgular var",
    "disk_findings_title": "Yeni bulgular",
    "disk_find_grew": "{name} {size} büyüdü",
    "disk_find_free": "Boş alan {free} (sınır {limit})",
    "disk_find_stale": "{name}: {size}, {days} gündür kullanılmıyor",
    "disk_find_mei": "Temp'te {count} yeni _MEI klasörü",
    "disk_gemini_prompt": "Aşağıdaki her klasör ya da program için en fazla 12 kelimelik Türkçe bir cümleyle ne "
                          "olduğunu söyle ve silinince yeniden indirilip kurulamayacak bir şey kaybolur mu, belirt. "
                          "Sadece JSON ile cevap ver: [{{\"id\": sayı, \"what\": metin, \"redownloadable\": true ya "
                          "da false}}] biçiminde bir liste.\n\n{items}",
})


# User Care (user_care, care_windows) and the panel's Care tab (care_panel). Texts ending in _happy /
# _normal / _angry / _worried follow her mood (worried: an angry mood late at night).
STRINGS["en"].update({
    "credits_source_care": "User Care",
    "panel_tab_care": "Care",
    "care_level_happy": "happy",
    "care_level_normal": "normal",
    "care_level_angry": "angry",
    "care_recent": "recent events",
    "care_last_exit": "last emergency exit",
    "care_ok": "OK",
    "care_break_title": "Break time",
    "care_take_break": "Take a break",
    "care_snooze": "Snooze",
    "care_break_window_title": "Break",
    "care_break_window": "{minutes} minutes away from the screen. Water, stretch, window. I'm counting.",
    "care_back": "I'm back",
    "care_forced_warning_title": "Forced break coming",
    "care_forced_warning": "No snoozes left. A forced break starts in {minutes} minutes: save your work.",
    "care_forced_title": "Forced break",
    "care_emergency_exit": "Emergency exit",
    "care_reason_hint": "Write why (she will remember it):",
    "care_water_title": "Water",
    "care_drank": "I drank",
    "care_later": "Later",
    "care_sleep_title": "Sleep",
    "care_sleep_soft": "It's {hour}. Still awake? Dim the screen, breathe slowly; I'm here.",
    "care_no_answer": "no answer",
    "care_classify_prompt": "At 3 a.m. the user was asked why they are still awake. Their answer: \"{answer}\"\n"
                            "Sort it into exactly one category: work (work, a deadline, a project, homework), exam "
                            "(an exam or studying for one), emergency (a real emergency), cant_sleep (they can't "
                            "fall asleep), whim (no real reason: gaming, videos, chatting, just because). "
                            "Reply with JSON only: {{\"category\": \"...\"}}",
    "care_shutdown_title": "Shutdown",
    "care_cancel_shutdown": "Cancel shutdown",
    "care_cancel": "Cancel",
    "care_final_title": "Shutting down",
    "care_final_text": "The PC shuts down when the countdown ends. Good night.",
    "care_shutdown_comment": "Zyraena: time to sleep (cancel: shutdown /a or /iptal on Telegram)",
    "care_dry_run_note": "(DRY_RUN: it won't really shut down, it's only logged.)",
    "care_dry_run_done": "DRY_RUN: the PC would have shut down now. Nothing was turned off.",
    "care_summary_fallback": "Good morning. Yesterday:\n{facts}",
    "care_fact_bed": "went to bed at {time}",
    "care_fact_bed_unknown": "bedtime unknown",
    "care_fact_breaks": "breaks: {taken} taken, {forced} forced, {away} away/asleep; {snoozed} snoozed, {unanswered} ignored",
    "care_fact_water": "water: {count} times",
    "care_fact_warnings": "sleep warnings: {count}",
    "care_fact_exits": "emergency exits: {count} ({reasons})",
    "care_fact_night": "03:00 answer: {category} -> {verdict}",
    "care_fact_cancels": "shutdowns cancelled: {count}",
    "care_cat_work": "work/deadline",
    "care_cat_exam": "exam",
    "care_cat_emergency": "emergency",
    "care_cat_cant_sleep": "can't sleep",
    "care_cat_whim": "no real reason",
    "care_verdict_valid": "accepted",
    "care_verdict_limit": "not accepted (weekly limit used up)",
    "care_verdict_cant_sleep": "no shutdown, be gentle",
    "care_verdict_invalid": "not accepted",
    "care_ev_reason": ", reason: \"{reason}\"",
    "care_ev_break_taken": "took a break",
    "care_ev_break_done": "break finished",
    "care_ev_break_back_early": "came back early from the break",
    "care_ev_snooze": "snoozed the break ({count} in a row)",
    "care_ev_unanswered": "ignored the break prompt ({count} in a row)",
    "care_ev_forced_warning": "forced break announced",
    "care_ev_forced_start": "forced break started",
    "care_ev_forced_done": "finished the forced break",
    "care_ev_emergency_exit": "left the forced break by the emergency exit",
    "care_ev_afk_break": "away for {minutes} min (counts as a break)",
    "care_ev_sleep": "PC asleep for {minutes} min (counts as a break)",
    "care_ev_water": "drank water",
    "care_ev_water_later": "put off the water",
    "care_ev_sleep_warning": "sleep warning at {hour}",
    "care_ev_night_asked": "asked why they're still up",
    "care_ev_night_reason": "night reason: {category} -> {verdict}",
    "care_ev_shutdown_warning": "step-by-step shutdown started ({minutes} min)",
    "care_ev_shutdown_protected": "forced break instead of a shutdown ({why})",
    "care_ev_shutdown_dry": "DRY_RUN: the PC would have shut down",
    "care_ev_shutdown": "PC shut down",
    "care_ev_shutdown_cancel": "cancelled the shutdown ({source})",
    "care_ev_bedtime": "went to bed at {time}",
    "care_ev_on_time_bed": "went to bed on time ({time})",
    "care_ev_peace": "made peace",
    "care_ev_morning_summary": "morning summary of {of}",
    "care_rule_program": "program",
    "care_rule_gpu": "GPU (compute/cuda)",
    "care_rule_terminal_jobs": "terminal job",
    "care_rule_training": "training project",
    "care_rule_zyraena_runs": "Zyraena's scripts",
    "care_rule_busy_cpu": "busy CPU",
    "care_rule_downloads": "download",
    "care_rule_downloads_net": "download (network)",
    "care_hm": "{h} h {m} min",
    "care_m": "{m} min",
    "care_status_mood": "Mood {mood}/100 · {level}",
    "care_status_active": "Active {active} · next break in {next} ({kind}) · snoozes {snoozes}/{rights}",
    "care_status_forced": "forced",
    "care_status_normal": "prompt",
    "care_status_water": "Water in {next}",
    "care_status_night": "Tonight: {night} · good reasons this week {used}/{limit}",
    "care_status_night_none": "-",
    "care_status_night_asked": "asked, waiting for the answer",
    "care_status_night_valid": "reason accepted",
    "care_status_night_limit": "reason not accepted (limit)",
    "care_status_night_cant_sleep": "can't sleep",
    "care_status_night_invalid": "no good reason",
    "care_status_breaking_normal": "On a break now",
    "care_status_breaking_forced": "Forced break now",
    "care_status_shutdown": "Step-by-step shutdown running",
    "care_status_dry_run": "DRY_RUN on (no real shutdown)",
    "care_status_live": "Real shutdowns ON",
    "care_status_fake": "debug clock {time}",
    "care_protect_title": "Protection (the PC is never shut down while one holds)",
    "care_protect_settings": "Protection settings…",
    "care_protect_none": "Nothing protected right now: a shutdown would go ahead.",
    "care_protect_on": "Protected: {why}",
    "care_protect_window": "Protection settings",
    "care_protect_explain": "While a rule holds, User Care never shuts the PC down: a forced break comes instead. "
                            "Breaks and reminders go on either way.",
    "care_protect_programs": "Programs (exe names)",
    "care_protect_patterns": "Training (text in a Python command line)",
    "care_limit_gpu_percent": "GPU %",
    "care_limit_gpu_minutes": "GPU min",
    "care_limit_gpu_compute_percent": "compute %",
    "care_limit_terminal_jobs_cpu_percent": "terminal CPU %",
    "care_limit_terminal_jobs_minutes": "terminal min",
    "care_limit_busy_cpu_percent": "busy CPU %",
    "care_limit_busy_cpu_minutes": "busy CPU min",
    "care_limit_downloads_mb_per_second": "MB/s",
    "care_limit_downloads_minutes": "download min",
    "care_add": "Add",
    "care_remove": "Remove",
    "care_save": "Save",
    "care_saving": "Saving…",
    "care_saved": "Saved to config.json.",
    "care_close": "Close",
    "care_bad_number": "Limits must be numbers.",
    "care_events_title": "Last events",
    "care_debug": "debug:",
    "care_debug_plus10": "+10 min",
    "care_debug_plus60": "+1 h",
    "care_debug_at0259": "02:59",
    "care_debug_at2359": "23:59",
    "care_debug_at0601": "06:01",
    "care_debug_away": "away 11 min",
    "care_debug_sleep": "sleep 30 min",
    "care_debug_active178": "active 178 min",
    "care_debug_mood_down": "mood -20",
    "care_debug_mood_up": "mood +20",
    "care_hint": "Settings: config.json, \"user_care\" · Esc closes",
})
STRINGS["tr"].update({
    "credits_source_care": "User Care",
    "panel_tab_care": "Bakım",
    "care_level_happy": "mutlu",
    "care_level_normal": "normal",
    "care_level_angry": "sinirli",
    "care_recent": "son olaylar",
    "care_last_exit": "son acil çıkış",
    "care_ok": "Tamam",
    "care_break_title": "Mola zamanı",
    "care_take_break": "Mola ver",
    "care_snooze": "Ertele",
    "care_break_window_title": "Mola",
    "care_break_window": "{minutes} dakika ekrandan uzak. Su, esneme, pencere. Sayıyorum.",
    "care_back": "Döndüm",
    "care_forced_warning_title": "Zorunlu mola geliyor",
    "care_forced_warning": "Erteleme hakkın bitti. {minutes} dakika sonra zorunlu mola: işini kaydet.",
    "care_forced_title": "Zorunlu mola",
    "care_emergency_exit": "Acil çıkış",
    "care_reason_hint": "Sebebini yaz (unutmayacak):",
    "care_water_title": "Su",
    "care_drank": "İçtim",
    "care_later": "Sonra",
    "care_sleep_title": "Uyku",
    "care_sleep_soft": "Saat {hour}. Hâlâ uyanık mısın? Ekranı karart, yavaş nefes al; buradayım.",
    "care_no_answer": "cevap yok",
    "care_classify_prompt": "Kullanıcıya gece saat 03:00'te neden hâlâ uyumadığı soruldu. Cevabı: \"{answer}\"\n"
                            "Cevabı tam olarak bir kategoriye ayır: work (iş, deadline, proje, ödev), exam (sınav ya "
                            "da sınava çalışma), emergency (gerçek bir acil durum), cant_sleep (uyuyamıyor, uykusu "
                            "gelmiyor), whim (gerçek bir sebep yok: oyun, dizi, sohbet, canı istedi). "
                            "Sadece JSON ile cevap ver: {{\"category\": \"...\"}}",
    "care_shutdown_title": "Kapatma",
    "care_cancel_shutdown": "Kapatmayı iptal et",
    "care_cancel": "İptal",
    "care_final_title": "Kapanıyor",
    "care_final_text": "Geri sayım bitince PC kapanacak. İyi geceler.",
    "care_shutdown_comment": "Zyraena: uyku vakti (iptal: shutdown /a ya da Telegram'da /iptal)",
    "care_dry_run_note": "(DRY_RUN: gerçekten kapanmayacak, sadece kayda geçiyor.)",
    "care_dry_run_done": "DRY_RUN: PC şimdi kapanacaktı. Hiçbir şey kapatılmadı.",
    "care_summary_fallback": "Günaydın. Dün:\n{facts}",
    "care_fact_bed": "{time}'da yattın",
    "care_fact_bed_unknown": "yatış saati bilinmiyor",
    "care_fact_breaks": "molalar: {taken} verildi, {forced} zorunlu, {away} uzakta/uykuda; {snoozed} ertelendi, {unanswered} cevapsız",
    "care_fact_water": "su: {count} kez",
    "care_fact_warnings": "uyku uyarısı: {count}",
    "care_fact_exits": "acil çıkış: {count} ({reasons})",
    "care_fact_night": "03:00 cevabı: {category} -> {verdict}",
    "care_fact_cancels": "iptal edilen kapatma: {count}",
    "care_cat_work": "iş/deadline",
    "care_cat_exam": "sınav",
    "care_cat_emergency": "acil durum",
    "care_cat_cant_sleep": "uyuyamıyorum",
    "care_cat_whim": "keyfi",
    "care_verdict_valid": "kabul edildi",
    "care_verdict_limit": "kabul edilmedi (haftalık hak doldu)",
    "care_verdict_cant_sleep": "kapatma yok, şefkat",
    "care_verdict_invalid": "kabul edilmedi",
    "care_ev_reason": ", sebep: \"{reason}\"",
    "care_ev_break_taken": "mola verdi",
    "care_ev_break_done": "mola bitti",
    "care_ev_break_back_early": "moladan erken döndü",
    "care_ev_snooze": "molayı erteledi (art arda {count})",
    "care_ev_unanswered": "mola uyarısını cevapsız bıraktı (art arda {count})",
    "care_ev_forced_warning": "zorunlu mola duyuruldu",
    "care_ev_forced_start": "zorunlu mola başladı",
    "care_ev_forced_done": "zorunlu molayı tamamladı",
    "care_ev_emergency_exit": "zorunlu moladan acil çıkışla çıktı",
    "care_ev_afk_break": "{minutes} dk uzaktaydı (mola sayıldı)",
    "care_ev_sleep": "PC {minutes} dk uykudaydı (mola sayıldı)",
    "care_ev_water": "su içti",
    "care_ev_water_later": "suyu erteledi",
    "care_ev_sleep_warning": "{hour} uyku uyarısı",
    "care_ev_night_asked": "neden yatmadığını sordum",
    "care_ev_night_reason": "gece sebebi: {category} -> {verdict}",
    "care_ev_shutdown_warning": "kademeli kapatma başladı ({minutes} dk)",
    "care_ev_shutdown_protected": "kapatma yerine zorunlu mola ({why})",
    "care_ev_shutdown_dry": "DRY_RUN: PC kapanacaktı",
    "care_ev_shutdown": "PC kapatıldı",
    "care_ev_shutdown_cancel": "kapatmayı iptal etti ({source})",
    "care_ev_bedtime": "{time}'da yattı",
    "care_ev_on_time_bed": "zamanında yattı ({time})",
    "care_ev_peace": "barıştık",
    "care_ev_morning_summary": "{of} günün sabah özeti",
    "care_rule_program": "program",
    "care_rule_gpu": "GPU (compute/cuda)",
    "care_rule_terminal_jobs": "terminal işi",
    "care_rule_training": "eğitim projesi",
    "care_rule_zyraena_runs": "Zyraena'nın script'leri",
    "care_rule_busy_cpu": "yoğun CPU",
    "care_rule_downloads": "indirme",
    "care_rule_downloads_net": "indirme (ağ)",
    "care_hm": "{h} sa {m} dk",
    "care_m": "{m} dk",
    "care_status_mood": "Mood {mood}/100 · {level}",
    "care_status_active": "Aktif {active} · sıradaki mola {next} sonra ({kind}) · erteleme {snoozes}/{rights}",
    "care_status_forced": "zorunlu",
    "care_status_normal": "uyarı",
    "care_status_water": "Su {next} sonra",
    "care_status_night": "Bu gece: {night} · bu hafta geçerli sebep {used}/{limit}",
    "care_status_night_none": "-",
    "care_status_night_asked": "soruldu, cevap bekleniyor",
    "care_status_night_valid": "sebep kabul edildi",
    "care_status_night_limit": "sebep kabul edilmedi (hak doldu)",
    "care_status_night_cant_sleep": "uyuyamıyor",
    "care_status_night_invalid": "geçerli sebep yok",
    "care_status_breaking_normal": "Şu an molada",
    "care_status_breaking_forced": "Şu an zorunlu molada",
    "care_status_shutdown": "Kademeli kapatma sürüyor",
    "care_status_dry_run": "DRY_RUN açık (gerçek kapatma yok)",
    "care_status_live": "Gerçek kapatma AÇIK",
    "care_status_fake": "debug saati {time}",
    "care_protect_title": "Koruma (biri varken PC asla kapatılmaz)",
    "care_protect_settings": "Koruma ayarları…",
    "care_protect_none": "Şu an koruma yok: kapatma gerekirse yapılır.",
    "care_protect_on": "Korunuyor: {why}",
    "care_protect_window": "Koruma ayarları",
    "care_protect_explain": "Kurallardan biri tutarken User Care PC'yi asla kapatmaz, onun yerine zorunlu mola "
                            "gelir. Molalar ve hatırlatmalar her durumda devam eder.",
    "care_protect_programs": "Programlar (exe adları)",
    "care_protect_patterns": "Eğitim (Python komut satırında geçen metin)",
    "care_limit_gpu_percent": "GPU %",
    "care_limit_gpu_minutes": "GPU dk",
    "care_limit_gpu_compute_percent": "compute %",
    "care_limit_terminal_jobs_cpu_percent": "terminal CPU %",
    "care_limit_terminal_jobs_minutes": "terminal dk",
    "care_limit_busy_cpu_percent": "yoğun CPU %",
    "care_limit_busy_cpu_minutes": "yoğun CPU dk",
    "care_limit_downloads_mb_per_second": "MB/sn",
    "care_limit_downloads_minutes": "indirme dk",
    "care_add": "Ekle",
    "care_remove": "Sil",
    "care_save": "Kaydet",
    "care_saving": "Kaydediliyor…",
    "care_saved": "config.json'a kaydedildi.",
    "care_close": "Kapat",
    "care_bad_number": "Sınırlar sayı olmalı.",
    "care_events_title": "Son olaylar",
    "care_debug": "debug:",
    "care_debug_plus10": "+10 dk",
    "care_debug_plus60": "+1 sa",
    "care_debug_at0259": "02:59",
    "care_debug_at2359": "23:59",
    "care_debug_at0601": "06:01",
    "care_debug_away": "uzakta 11 dk",
    "care_debug_sleep": "uyku 30 dk",
    "care_debug_active178": "aktif 178 dk",
    "care_debug_mood_down": "mood -20",
    "care_debug_mood_up": "mood +20",
    "care_hint": "Ayarlar: config.json, \"user_care\" · Esc kapatır",
})


# --- Her lines by mood ----------------------------------------------------------------------------------
# The pet's lines are pet_lines[_<pose>]_<mood> (happy, normal, angry; worried for the plain ones; a mood
# without its own falls back to normal, then happy); User Care's are care_<what>_<tone>. Every line is one
# variant, picked at random. {user} is the owner's name (user_name()).
# This is the example: copy it to i18n.py (gitignored) and write her lines there, as many per key as you like.

USER_FALLBACK = "Operator"  # when ZYRAENA_USER_NAME isn't set

# How the mood colours her replies in the lady persona (User Care's prompt block).
PERSONA_TONES = "happy: warmer teasing; normal: your usual self; angry: cold and sharp"

MOOD_LINES = {
    "en": {
        "pet_lines_happy": [
            "Need anything, {user}?"
        ],
        "pet_lines_normal": [
            "Need anything, {user}?"
        ],
        "pet_lines_angry": [
            "Need anything, {user}?"
        ],
        "pet_lines_code_happy": [
            "Keep going, {user}."
        ],
        "pet_lines_code_normal": [
            "Keep going, {user}."
        ],
        "pet_lines_code_angry": [
            "Keep going, {user}."
        ],
        "pet_lines_watch_happy": [
            "Interesting."
        ],
        "pet_lines_watch_normal": [
            "Interesting."
        ],
        "pet_lines_watch_angry": [
            "Interesting."
        ],
        "pet_lines_lift_happy": [
            "This is light."
        ],
        "pet_lines_lift_normal": [
            "This is light."
        ],
        "pet_lines_lift_angry": [
            "This is light."
        ],
        "pet_lines_dagger_happy": [
            "Drow steel."
        ],
        "pet_lines_dagger_normal": [
            "Drow steel."
        ],
        "pet_lines_dagger_angry": [
            "Drow steel."
        ],
        "pet_lines_stretch_happy": [
            "Stretch a little, {user}."
        ],
        "pet_lines_stretch_normal": [
            "Stretch a little, {user}."
        ],
        "pet_lines_stretch_angry": [
            "Stretch a little, {user}."
        ],
        "pet_lines_impatient_happy": [
            "I'm waiting, {user}."
        ],
        "pet_lines_impatient_normal": [
            "I'm waiting, {user}."
        ],
        "pet_lines_impatient_angry": [
            "I'm waiting, {user}."
        ],
        "pet_lines_worried": [
            "It's late. Get some sleep."
        ],
        "care_break_prompt_happy": [
            "{minutes} minutes at the screen. Time for a break."
        ],
        "care_break_prompt_normal": [
            "{minutes} minutes at the screen. Time for a break."
        ],
        "care_break_prompt_angry": [
            "{minutes} minutes at the screen. Time for a break."
        ],
        "care_break_prompt_worried": [
            "{minutes} minutes at the screen. Time for a break."
        ],
        "care_forced_text_happy": [
            "No more snoozing. {minutes} minutes away from the screen."
        ],
        "care_forced_text_normal": [
            "No more snoozing. {minutes} minutes away from the screen."
        ],
        "care_forced_text_angry": [
            "No more snoozing. {minutes} minutes away from the screen."
        ],
        "care_forced_text_worried": [
            "No more snoozing. {minutes} minutes away from the screen."
        ],
        "care_break_over_happy": [
            "Break's over."
        ],
        "care_break_over_normal": [
            "Break's over."
        ],
        "care_break_over_angry": [
            "Break's over."
        ],
        "care_break_over_worried": [
            "Break's over."
        ],
        "care_water_happy": [
            "Time for some water."
        ],
        "care_water_normal": [
            "Time for some water."
        ],
        "care_water_angry": [
            "Time for some water."
        ],
        "care_water_worried": [
            "Time for some water."
        ],
        "care_sleep_warning_happy": [
            "It's {hour}. Time to sleep."
        ],
        "care_sleep_warning_normal": [
            "It's {hour}. Time to sleep."
        ],
        "care_sleep_warning_angry": [
            "It's {hour}. Time to sleep."
        ],
        "care_sleep_warning_worried": [
            "It's {hour}. Time to sleep."
        ],
        "care_night_question_happy": [
            "It's 03:00. Why are you still up? Answer within {minutes} minutes."
        ],
        "care_night_question_normal": [
            "It's 03:00. Why are you still up? Answer within {minutes} minutes."
        ],
        "care_night_question_angry": [
            "It's 03:00. Why are you still up? Answer within {minutes} minutes."
        ],
        "care_night_question_worried": [
            "It's 03:00. Why are you still up? Answer within {minutes} minutes."
        ],
        "care_shutdown_warning_happy": [
            "The PC shuts down in {minutes} minutes. Save your work."
        ],
        "care_shutdown_warning_normal": [
            "The PC shuts down in {minutes} minutes. Save your work."
        ],
        "care_shutdown_warning_angry": [
            "The PC shuts down in {minutes} minutes. Save your work."
        ],
        "care_shutdown_warning_worried": [
            "The PC shuts down in {minutes} minutes. Save your work."
        ]
    },
    "tr": {
        "pet_lines_happy": [
            "Bir şey lazım mı, {user}?"
        ],
        "pet_lines_normal": [
            "Bir şey lazım mı, {user}?"
        ],
        "pet_lines_angry": [
            "Bir şey lazım mı, {user}?"
        ],
        "pet_lines_code_happy": [
            "Devam et, {user}."
        ],
        "pet_lines_code_normal": [
            "Devam et, {user}."
        ],
        "pet_lines_code_angry": [
            "Devam et, {user}."
        ],
        "pet_lines_watch_happy": [
            "İlginç."
        ],
        "pet_lines_watch_normal": [
            "İlginç."
        ],
        "pet_lines_watch_angry": [
            "İlginç."
        ],
        "pet_lines_lift_happy": [
            "Bu hafif."
        ],
        "pet_lines_lift_normal": [
            "Bu hafif."
        ],
        "pet_lines_lift_angry": [
            "Bu hafif."
        ],
        "pet_lines_dagger_happy": [
            "Drow çeliği."
        ],
        "pet_lines_dagger_normal": [
            "Drow çeliği."
        ],
        "pet_lines_dagger_angry": [
            "Drow çeliği."
        ],
        "pet_lines_stretch_happy": [
            "Biraz gerin, {user}."
        ],
        "pet_lines_stretch_normal": [
            "Biraz gerin, {user}."
        ],
        "pet_lines_stretch_angry": [
            "Biraz gerin, {user}."
        ],
        "pet_lines_impatient_happy": [
            "Bekliyorum, {user}."
        ],
        "pet_lines_impatient_normal": [
            "Bekliyorum, {user}."
        ],
        "pet_lines_impatient_angry": [
            "Bekliyorum, {user}."
        ],
        "pet_lines_worried": [
            "Saat geç. Biraz uyu."
        ],
        "care_break_prompt_happy": [
            "{minutes} dakikadır ekrandasın. Mola zamanı."
        ],
        "care_break_prompt_normal": [
            "{minutes} dakikadır ekrandasın. Mola zamanı."
        ],
        "care_break_prompt_angry": [
            "{minutes} dakikadır ekrandasın. Mola zamanı."
        ],
        "care_break_prompt_worried": [
            "{minutes} dakikadır ekrandasın. Mola zamanı."
        ],
        "care_forced_text_happy": [
            "Erteleme hakkı bitti. {minutes} dakika ekrandan uzak dur."
        ],
        "care_forced_text_normal": [
            "Erteleme hakkı bitti. {minutes} dakika ekrandan uzak dur."
        ],
        "care_forced_text_angry": [
            "Erteleme hakkı bitti. {minutes} dakika ekrandan uzak dur."
        ],
        "care_forced_text_worried": [
            "Erteleme hakkı bitti. {minutes} dakika ekrandan uzak dur."
        ],
        "care_break_over_happy": [
            "Mola bitti."
        ],
        "care_break_over_normal": [
            "Mola bitti."
        ],
        "care_break_over_angry": [
            "Mola bitti."
        ],
        "care_break_over_worried": [
            "Mola bitti."
        ],
        "care_water_happy": [
            "Su içme vakti."
        ],
        "care_water_normal": [
            "Su içme vakti."
        ],
        "care_water_angry": [
            "Su içme vakti."
        ],
        "care_water_worried": [
            "Su içme vakti."
        ],
        "care_sleep_warning_happy": [
            "Saat {hour}. Uyku vakti."
        ],
        "care_sleep_warning_normal": [
            "Saat {hour}. Uyku vakti."
        ],
        "care_sleep_warning_angry": [
            "Saat {hour}. Uyku vakti."
        ],
        "care_sleep_warning_worried": [
            "Saat {hour}. Uyku vakti."
        ],
        "care_night_question_happy": [
            "Saat 03:00. Neden hâlâ ayaktasın? {minutes} dakika içinde cevap ver."
        ],
        "care_night_question_normal": [
            "Saat 03:00. Neden hâlâ ayaktasın? {minutes} dakika içinde cevap ver."
        ],
        "care_night_question_angry": [
            "Saat 03:00. Neden hâlâ ayaktasın? {minutes} dakika içinde cevap ver."
        ],
        "care_night_question_worried": [
            "Saat 03:00. Neden hâlâ ayaktasın? {minutes} dakika içinde cevap ver."
        ],
        "care_shutdown_warning_happy": [
            "PC {minutes} dakika sonra kapanıyor. İşini kaydet."
        ],
        "care_shutdown_warning_normal": [
            "PC {minutes} dakika sonra kapanıyor. İşini kaydet."
        ],
        "care_shutdown_warning_angry": [
            "PC {minutes} dakika sonra kapanıyor. İşini kaydet."
        ],
        "care_shutdown_warning_worried": [
            "PC {minutes} dakika sonra kapanıyor. İşini kaydet."
        ]
    }
}
for _lang, _lines in MOOD_LINES.items():
    STRINGS[_lang].update({key: "\n".join(lines) for key, lines in _lines.items()})
# --- end of her lines by mood ---------------------------------------------------------------------------


def user_name() -> str:
    """The owner's name in her lines ({user}): ZYRAENA_USER_NAME from .env, else USER_FALLBACK."""
    return os.environ.get("ZYRAENA_USER_NAME", "").strip() or USER_FALLBACK


def get(language: str, key: str, **kwargs) -> str:
    table = STRINGS.get(language, STRINGS[DEFAULT_LANGUAGE])
    text = table.get(key, STRINGS[DEFAULT_LANGUAGE].get(key, key))
    return text.format(**kwargs) if kwargs else text


def render(language: str, keys, **kwargs) -> str:
    """Like get, but `keys` may be a list of keys whose texts are joined as paragraphs."""
    if isinstance(keys, str):
        keys = [keys]
    return "\n\n".join(get(language, key, **kwargs) for key in keys)
