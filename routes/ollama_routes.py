from flask import Blueprint, render_template, request, flash
from flask_login import login_required
from openai import OpenAI
import os

ollama_bp = Blueprint('ollama', __name__, url_prefix='/ollama')

USE_OLLAMA = os.getenv('USE_OLLAMA', 'false').lower() == 'true'
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1:8b')
OLLAMA_BASE_URL = 'http://127.0.0.1:11434/v1'

@ollama_bp.route('/assistant', methods=['GET', 'POST'])
@login_required
def ai_assistant():
    answer = ""
    question = ""

    if request.method == 'POST':
        question = request.form.get('question', '').strip()

        if not question:
            flash('Напишите ваш вопрос в техподдержку', 'warning')
        elif not USE_OLLAMA:
            flash('ИИ Ассистент временно недоступен', 'info')
        else:
            try:
                client = OpenAI(
                    base_url=OLLAMA_BASE_URL,
                    api_key="ollama",
                )

                response = client.chat.completions.create(
                    model=OLLAMA_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты — ИИ Ассистент техподдержки системы учёта посещаемости Финансово-экономического колледжа РИНХ. "
                                       "Отвечай вежливо, профессионально, кратко и по делу. "
                                       "Помогай пользователям (администраторам, кураторам, старостам) с вопросами о работе сайта, "
                                       "студентах, группах, пропусках, подтверждениях, статистике и настройках. "
                                       "Если не знаешь — честно говори 'не могу ответить, обратитесь к администратору'."
                        },
                        {"role": "user", "content": question}
                    ],
                    temperature=0.6,
                    max_tokens=1200
                )

                answer = response.choices[0].message.content.strip()

            except Exception as e:
                flash(f'Ошибка связи с ИИ Ассистентом: {str(e)}', 'danger')

    return render_template(
        'ai_assistant.html',
        question=question,
        answer=answer,
        use_ollama=USE_OLLAMA,
        current_model=OLLAMA_MODEL
    )