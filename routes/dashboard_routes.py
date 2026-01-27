# routes/dashboard_routes.py
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from db import db
from models.student import Student
from models.group import Group
from models.absence import Absence
from models.user import User
from models.cmk import Cmk
from models.audit_log import AuditLog
from datetime import datetime, timedelta
import pandas as pd
import io
import csv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import logging

dashboard_bp = Blueprint('dashboard', __name__)

# =============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================

def get_user_groups(user):
    """Возвращает список групп доступных пользователю"""
    if user.role == 'admin':
        return Group.query.all()
    elif user.role == 'curator':
        return Group.query.filter_by(curator_id=user.id).all()
    elif user.role == 'leader':
        group = Group.query.filter_by(leader_id=user.id).first()
        return [group] if group else []
    return []

def get_user_students(user):
    """Возвращает список студентов доступных пользователю"""
    if user.role == 'admin':
        return Student.query.all()
    elif user.role == 'curator':
        groups = Group.query.filter_by(curator_id=user.id).all()
        group_ids = [g.id for g in groups]
        return Student.query.filter(Student.group_id.in_(group_ids)).all() if group_ids else []
    elif user.role == 'leader':
        group = Group.query.filter_by(leader_id=user.id).first()
        return Student.query.filter_by(group_id=group.id).all() if group else []
    return []

def get_user_absences(user):
    """Возвращает список пропусков доступных пользователю"""
    if user.role == 'admin':
        return Absence.query.all()
    elif user.role == 'curator':
        groups = Group.query.filter_by(curator_id=user.id).all()
        group_ids = [g.id for g in groups]
        students = Student.query.filter(Student.group_id.in_(group_ids)).all() if group_ids else []
        student_ids = [s.id for s in students]
        return Absence.query.filter(Absence.student_id.in_(student_ids)).all() if student_ids else []
    elif user.role == 'leader':
        group = Group.query.filter_by(leader_id=user.id).first()
        if group:
            students = Student.query.filter_by(group_id=group.id).all()
            student_ids = [s.id for s in students]
            return Absence.query.filter(Absence.student_id.in_(student_ids)).all() if student_ids else []
    return []

# =============================================
# ОСНОВНЫЕ МАРШРУТЫ
# =============================================

@dashboard_bp.route('/')
@login_required
def index():
    pending_count = 0
    if current_user.role == 'admin':
        pending_count = User.query.filter(
            User.role.in_(['curator', 'leader']),
            User.is_confirmed == False,
            User.is_rejected == False
        ).count()

    return render_template(
        'dashboard.html',
        user=current_user,
        students_count=Student.query.count(),
        groups_count=Group.query.count(),
        absences_count=Absence.query.count(),
        pending_count=pending_count
    )

# =============================================
# АДМИН-ПАНЕЛЬ И БЫСТРЫЕ ДЕЙСТВИЯ
# =============================================

@dashboard_bp.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Статистика для админа
    stats = {
        'total_users': User.query.count(),
        'total_students': Student.query.count(),
        'total_groups': Group.query.count(),
        'total_absences': Absence.query.count(),
        'pending_users': User.query.filter_by(is_confirmed=False, is_rejected=False).count(),
        'curator_count': User.query.filter_by(role='curator', is_confirmed=True).count(),
        'leader_count': User.query.filter_by(role='leader', is_confirmed=True).count(),
        'today_absences': Absence.query.filter(Absence.date == datetime.now().date()).count()
    }
    
    # Последние 5 действий
    recent_actions = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(5).all()
    
    # Получаем всех пользователей для отображения в таблице
    all_users = User.query.all()
    
    # Получаем ожидающих подтверждения
    pending_users = User.query.filter_by(is_confirmed=False, is_rejected=False).all()
    
    return render_template('admin_dashboard.html', 
                         stats=stats, 
                         recent_actions=recent_actions,
                         all_users=all_users,
                         pending_users=pending_users,
                         total_users=stats['total_users'],
                         total_students=stats['total_students'],
                         total_groups=stats['total_groups'],
                         pending_users_count=stats['pending_users'])

# =============================================
# БЫСТРЫЕ ДЕЙСТВИЯ АДМИНИСТРАТОРА
# =============================================

@dashboard_bp.route('/admin/quick-actions')
@login_required
def admin_quick_actions():
    """Страница быстрых действий администратора"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    return render_template('admin_quick_actions.html')

# =============================================
# ПОДТВЕРЖДЕНИЕ ПОЛЬЗОВАТЕЛЕЙ
# =============================================

@dashboard_bp.route('/confirm_users')
@login_required
def confirm_users():
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Получаем всех неподтверждённых пользователей
    pending_users = User.query.filter(
        User.role.in_(['curator', 'leader']),
        User.is_confirmed == False,
        User.is_rejected == False
    ).all()
    
    # Разделяем на кураторов и старост
    pending_curators = [u for u in pending_users if u.role == 'curator']
    pending_leaders = [u for u in pending_users if u.role == 'leader']
    
    return render_template('confirm_users.html', 
                         pending_curators=pending_curators,
                         pending_leaders=pending_leaders,
                         all_pending=pending_users)

@dashboard_bp.route('/confirm_curators')
@login_required
def confirm_curators():
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Получаем только неподтверждённых кураторов
    pending_curators = User.query.filter(
        User.role == 'curator',
        User.is_confirmed == False,
        User.is_rejected == False
    ).all()
    
    return render_template('confirm_curators.html', curators=pending_curators)

@dashboard_bp.route('/confirm_leaders')
@login_required
def confirm_leaders():
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Получаем только неподтверждённых старост
    pending_leaders = User.query.filter(
        User.role == 'leader',
        User.is_confirmed == False,
        User.is_rejected == False
    ).all()
    
    # Получаем информацию о группах для старост
    leaders_with_groups = []
    for leader in pending_leaders:
        group = Group.query.filter_by(leader_id=leader.id).first() if leader.role == 'leader' else None
        leaders_with_groups.append({
            'id': leader.id,
            'full_name': leader.full_name,
            'phone': leader.phone,
            'email': leader.email,
            'group': group
        })
    
    return render_template('confirm_leaders.html', leaders=leaders_with_groups)

@dashboard_bp.route('/confirm_user/<int:user_id>')
@login_required
def confirm_user(user_id):
    """Подтверждение пользователя (куратора или старосты)"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    user = User.query.get_or_404(user_id)
    
    if user.role not in ['curator', 'leader']:
        flash('Пользователь не является куратором или старостой', 'danger')
        return redirect(url_for('dashboard.confirm_users'))
    
    user.is_confirmed = True
    user.confirmed_at = datetime.utcnow()
    user.confirmed_by_id = current_user.id
    db.session.commit()
    
    # Логируем действие
    audit_log = AuditLog(
        user_id=current_user.id,
        action='confirm_user',
        description=f'Подтверждён пользователь: {user.full_name} ({user.role})',
        ip_address=request.remote_addr
    )
    db.session.add(audit_log)
    db.session.commit()
    
    flash(f'Пользователь {user.full_name} подтверждён', 'success')
    
    # Редирект в зависимости от роли
    if user.role == 'curator':
        return redirect(url_for('dashboard.confirm_curators'))
    else:
        return redirect(url_for('dashboard.confirm_leaders'))

@dashboard_bp.route('/confirm_curator/<int:curator_id>')
@login_required
def confirm_curator(curator_id):
    """Подтверждение конкретного куратора"""
    return confirm_user(curator_id)

@dashboard_bp.route('/confirm_leader/<int:user_id>')
@login_required
def confirm_leader(user_id):
    """Подтверждение конкретного старосты"""
    return confirm_user(user_id)

@dashboard_bp.route('/reject_user/<int:user_id>')
@login_required
def reject_user(user_id):
    """Отклонение пользователя"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    user = User.query.get_or_404(user_id)
    
    user.is_rejected = True
    user.rejected_at = datetime.utcnow()
    user.rejected_by_id = current_user.id
    db.session.commit()
    
    # Логируем действие
    audit_log = AuditLog(
        user_id=current_user.id,
        action='reject_user',
        description=f'Отклонён пользователь: {user.full_name} ({user.role})',
        ip_address=request.remote_addr
    )
    db.session.add(audit_log)
    db.session.commit()
    
    flash(f'Заявка пользователя {user.full_name} отклонена', 'success')
    
    # Редирект в зависимости от роли
    if user.role == 'curator':
        return redirect(url_for('dashboard.confirm_curators'))
    else:
        return redirect(url_for('dashboard.confirm_leaders'))

# =============================================
# СТАТИСТИКА
# =============================================

@dashboard_bp.route('/curator_stats')
@login_required
def curator_stats():
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Получаем всех подтверждённых кураторов и старост
    users = User.query.filter(
        User.role.in_(['curator', 'leader']),
        User.is_confirmed == True
    ).all()
    
    # Собираем статистику
    curator_data = []
    for user in users:
        groups_count = 0
        students_count = 0
        total_absences = 0
        excused = 0
        unexcused = 0
        
        if user.role == 'curator':
            groups = Group.query.filter_by(curator_id=user.id).all()
            groups_count = len(groups)
            for group in groups:
                students_count += len(group.students)
                for student in group.students:
                    absences = Absence.query.filter_by(student_id=student.id).all()
                    total_absences += len(absences)
                    for absence in absences:
                        if absence.reason and absence.reason.lower() in ['болезнь', 'справка', 'уважительная']:
                            excused += 1
                        else:
                            unexcused += 1
        else:  # leader
            group = Group.query.filter_by(leader_id=user.id).first()
            if group:
                groups_count = 1
                students_count = len(group.students)
                for student in group.students:
                    absences = Absence.query.filter_by(student_id=student.id).all()
                    total_absences += len(absences)
                    for absence in absences:
                        if absence.reason and absence.reason.lower() in ['болезнь', 'справка', 'уважительная']:
                            excused += 1
                        else:
                            unexcused += 1
        
        curator_data.append({
            'curator': user.full_name,
            'role': user.role,
            'phone': user.phone,
            'telegram': user.telegram,
            'groups_count': groups_count,
            'students_count': students_count,
            'total_absences': total_absences,
            'excused': excused,
            'unexcused': unexcused
        })
    
    return render_template('curator_stats.html', curator_data=curator_data)

@dashboard_bp.route('/cmk_stats')
@login_required
def cmk_stats():
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    cmks = Cmk.query.all()
    
    # Собираем статистику по ЦМК
    cmk_data = []
    for cmk in cmks:
        # Получаем кураторов ЦМК
        curators = User.query.filter_by(cmk_id=cmk.id, role='curator', is_confirmed=True).all()
        
        total_groups = 0
        total_students = 0
        total_absences = 0
        
        for curator in curators:
            groups = Group.query.filter_by(curator_id=curator.id).all()
            total_groups += len(groups)
            for group in groups:
                total_students += len(group.students)
                for student in group.students:
                    total_absences += Absence.query.filter_by(student_id=student.id).count()
        
        cmk_data.append({
            'cmk': cmk,
            'curator_count': len(curators),
            'groups_count': total_groups,
            'students_count': total_students,
            'absences_count': total_absences
        })
    
    return render_template('cmk_stats.html', cmk_data=cmk_data)

# =============================================
# ЭКСПОРТ СТУДЕНТОВ (НОВЫЙ РАСШИРЕННЫЙ ВАРИАНТ)
# =============================================

@dashboard_bp.route('/export-students', methods=['GET'])
@login_required
def export_students_page():
    """Расширенный экспорт студентов с фильтрами - страница формы"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Получаем группы и кураторов для фильтров
    groups = Group.query.all()
    curators = User.query.filter_by(role='curator', is_confirmed=True).all()
    
    # ПОЛУЧАЕМ ВСЕХ СТАРОСТ (leader) ДЛЯ ФИЛЬТРА
    headmen = User.query.filter_by(role='leader', is_confirmed=True).all()
    
    # Добавляем информацию о группе для каждого старосты
    headmen_with_groups = []
    for headman in headmen:
        group = Group.query.filter_by(leader_id=headman.id).first()
        headmen_with_groups.append({
            'id': headman.id,
            'full_name': headman.full_name,
            'group_name': group.name if group else 'Не назначена'
        })
    
    return render_template('export_students.html', 
                         groups=groups, 
                         curators=curators,
                         headmen=headmen_with_groups)  # Передаём список старост

@dashboard_bp.route('/export-students/process', methods=['POST'])
@login_required
def export_students_post():
    """Обработка экспорта студентов (POST запрос)"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    try:
        # Получаем параметры фильтрации
        group_id = request.form.get('group_id')
        curator_id = request.form.get('curator_id')
        headman_id = request.form.get('headman_id')  # Новый параметр для фильтра по старосте
        period = request.form.get('period', 'week')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        export_format = request.form.get('export_format', 'excel')
        include_stats = request.form.get('include_stats') == 'on'
        include_reason = request.form.get('include_reason') == 'on'
        exclude_status = request.form.get('exclude_status') == 'on'  # Новая опция
        
        # Строим запрос для получения студентов
        query = Student.query
        
        # Применяем фильтры
        if group_id and group_id != '':
            query = query.filter_by(group_id=group_id)
        
        if curator_id and curator_id != '':
            # Находим группы, курируемые выбранным куратором
            curator_groups = Group.query.filter_by(curator_id=curator_id).all()
            if curator_groups:
                curator_group_ids = [g.id for g in curator_groups]
                query = query.filter(Student.group_id.in_(curator_group_ids))
        
        # ДОБАВЛЯЕМ ФИЛЬТР ПО СТАРОСТЕ
        if headman_id and headman_id != '':
            # Находим группу, где выбранный пользователь является старостой
            leader_group = Group.query.filter_by(leader_id=headman_id).first()
            if leader_group:
                query = query.filter_by(group_id=leader_group.id)
        
        # Получаем студентов
        students = query.all()
        
        if not students:
            flash('Нет студентов, соответствующих выбранным фильтрам', 'warning')
            return redirect(url_for('dashboard.export_students_page'))
        
        # Определяем период для фильтрации пропусков
        end_date_obj = datetime.now()
        start_date_obj = None
        
        if period != 'all':
            if period == 'week':
                start_date_obj = end_date_obj - timedelta(days=7)
            elif period == 'month':
                start_date_obj = end_date_obj - timedelta(days=30)
            elif period == 'semester':
                start_date_obj = end_date_obj - timedelta(days=180)
            elif period == 'year':
                start_date_obj = end_date_obj - timedelta(days=365)
            elif period == 'custom' and start_date and end_date:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            else:
                start_date_obj = end_date_obj - timedelta(days=7)
        
        # Подготавливаем данные для экспорта
        data = []
        for student in students:
            student_data = {
                'ID': student.id,
                'ФИО': student.full_name,
                'Группа': student.group.name if student.group else '',
                'Телефон': student.phone or '',
                'Статус': 'Активен',
                'Куратор': student.group.curator.full_name if student.group and student.group.curator else '',
                'Староста': student.group.leader.full_name if student.group and student.group.leader else ''
            }
            
            # Убираем колонку "Статус" если нужно
            if exclude_status:
                del student_data['Статус']
            
            # Добавляем статистику пропусков если нужно
            if include_stats:
                if start_date_obj:
                    # Фильтрация пропусков по дате
                    absences_query = Absence.query.filter_by(student_id=student.id)
                    if start_date_obj:
                        absences_query = absences_query.filter(
                            Absence.date >= start_date_obj.date(),
                            Absence.date <= end_date_obj.date()
                        )
                    total_misses = absences_query.count()
                else:
                    total_misses = Absence.query.filter_by(student_id=student.id).count()
                
                student_data['Всего пропусков'] = total_misses
                
                if include_reason and total_misses > 0:
                    # Статистика по причинам
                    if start_date_obj:
                        reasons = db.session.query(Absence.reason, db.func.count(Absence.id))\
                                            .filter_by(student_id=student.id)\
                                            .filter(
                                                Absence.date >= start_date_obj.date(),
                                                Absence.date <= end_date_obj.date()
                                            )\
                                            .group_by(Absence.reason)\
                                            .all()
                    else:
                        reasons = db.session.query(Absence.reason, db.func.count(Absence.id))\
                                            .filter_by(student_id=student.id)\
                                            .group_by(Absence.reason)\
                                            .all()
                    
                    for reason, count in reasons:
                        if reason:
                            student_data[f'Пропуски ({reason})'] = count
                        else:
                            student_data['Пропуски без причины'] = count
            
            data.append(student_data)
        
        # Создаем DataFrame
        df = pd.DataFrame(data)
        
        # Логируем действие
        audit_log = AuditLog(
            user_id=current_user.id,
            action='export_students_extended',
            description=f'Экспорт студентов: {len(students)} записей в формате {export_format}',
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        # Создаем файл в зависимости от формата
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if export_format == 'excel':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Студенты', index=False)
                # Автонастройка ширины колонок
                worksheet = writer.sheets['Студенты']
                for column in df:
                    column_width = max(df[column].astype(str).map(len).max(), len(column))
                    col_idx = df.columns.get_loc(column)
                    worksheet.column_dimensions[chr(65 + col_idx)].width = min(column_width + 2, 50)
            
            output.seek(0)
            filename = f'students_export_{timestamp}.xlsx'
            return send_file(output, 
                           download_name=filename,
                           as_attachment=True,
                           mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        elif export_format == 'csv':
            output = io.BytesIO()
            df.to_csv(output, index=False, encoding='utf-8-sig')
            output.seek(0)
            filename = f'students_export_{timestamp}.csv'
            return send_file(output, 
                           download_name=filename,
                           as_attachment=True,
                           mimetype='text/csv')
        
        elif export_format == 'pdf':
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.pdfgen import canvas
                from reportlab.lib import colors
                from reportlab.platypus import Table, TableStyle
                from reportlab.lib.units import inch
            except ImportError:
                flash('Для экспорта в PDF установите библиотеку reportlab: pip install reportlab', 'danger')
                return redirect(url_for('dashboard.export_students_page'))
            
            output = io.BytesIO()
            c = canvas.Canvas(output, pagesize=A4)
            width, height = A4
            
            # Заголовок
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, height - 50, "Экспорт студентов")
            c.setFont("Helvetica", 10)
            c.drawString(50, height - 70, f"Дата экспорта: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
            c.drawString(50, height - 85, f"Всего записей: {len(students)}")
            
            if start_date_obj:
                c.drawString(50, height - 100, f"Период: {start_date_obj.strftime('%d.%m.%Y')} - {end_date_obj.strftime('%d.%m.%Y')}")
            
            # Подготавливаем данные для таблицы (ограничиваем колонки для PDF)
            pdf_data = []
            
            # Определяем какие колонки показывать
            columns_to_show = []
            if 'ФИО' in df.columns:
                columns_to_show.append('ФИО')
            if 'Группа' in df.columns:
                columns_to_show.append('Группа')
            if 'Телефон' in df.columns:
                columns_to_show.append('Телефон')
            if include_stats and 'Всего пропусков' in df.columns:
                columns_to_show.append('Всего пропусков')
            
            # Заголовки
            pdf_data.append(columns_to_show)
            
            # Данные
            for index, row in df.iterrows():
                pdf_row = []
                for col in columns_to_show:
                    value = row[col] if col in row else ''
                    pdf_row.append(str(value) if not pd.isna(value) else '')
                pdf_data.append(pdf_row)
            
            # Создаем таблицу
            col_widths = [2.5*inch] * len(columns_to_show)  # Базовая ширина
            if len(columns_to_show) >= 2:
                col_widths[1] = 1*inch  # Группа уже
            
            table = Table(pdf_data, repeatRows=1, colWidths=col_widths[:len(columns_to_show)])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            
            # Размещаем таблицу
            table.wrapOn(c, width - 100, height)
            table.drawOn(c, 50, 50)
            
            c.save()
            output.seek(0)
            filename = f'students_export_{timestamp}.pdf'
            return send_file(output, 
                           download_name=filename,
                           as_attachment=True,
                           mimetype='application/pdf')
        
        else:
            flash('Неверный формат экспорта', 'danger')
            return redirect(url_for('dashboard.export_students_page'))
            
    except Exception as e:
        db.session.rollback()
        logging.error(f"Export error: {str(e)}", exc_info=True)
        flash(f'Ошибка при экспорте: {str(e)}', 'danger')
        return redirect(url_for('dashboard.export_students_page'))

@dashboard_bp.route('/api/export-preview')
@login_required
def export_preview():
    """API для предварительного просмотра данных (реальные данные из БД)"""
    # Проверяем права доступа - возвращаем JSON, а не редирект
    if current_user.role != 'admin':
        return jsonify({
            'success': False, 
            'error': 'Доступ запрещен. Требуется роль администратора.',
            'students': [],
            'count': 0,
            'groups_count': 0,
            'stats': {
                'groups_count': 0,
                'students_count': 0,
                'absences_count': 0
            },
            'has_data': False
        }), 403
    
    try:
        # Получаем параметры из запроса
        group_id = request.args.get('group_id')
        curator_id = request.args.get('curator_id')
        headman_id = request.args.get('headman_id')  # Новый параметр
        period = request.args.get('period', 'week')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        include_stats = request.args.get('include_stats', 'false') == 'true'
        
        # Определяем период
        end_date_obj = datetime.now()
        start_date_obj = None
        
        if period != 'all':
            if period == 'week':
                start_date_obj = end_date_obj - timedelta(days=7)
            elif period == 'month':
                start_date_obj = end_date_obj - timedelta(days=30)
            elif period == 'semester':
                start_date_obj = end_date_obj - timedelta(days=180)
            elif period == 'year':
                start_date_obj = end_date_obj - timedelta(days=365)
            elif period == 'custom' and start_date and end_date:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            else:
                start_date_obj = end_date_obj - timedelta(days=7)
        
        query = Student.query
        
        if group_id and group_id != '':
            query = query.filter_by(group_id=group_id)
        
        if curator_id and curator_id != '':
            curator_groups = Group.query.filter_by(curator_id=curator_id).all()
            if curator_groups:
                curator_group_ids = [g.id for g in curator_groups]
                query = query.filter(Student.group_id.in_(curator_group_ids))
        
        # ДОБАВЛЯЕМ ФИЛЬТР ПО СТАРОСТЕ
        if headman_id and headman_id != '':
            leader_group = Group.query.filter_by(leader_id=headman_id).first()
            if leader_group:
                query = query.filter_by(group_id=leader_group.id)
        
        # Получаем реальные данные
        total_count = query.count()
        students = query.limit(10).all()
        
        preview_data = []
        total_absences = 0
        
        for student in students:
            # Считаем пропуски
            absences_query = Absence.query.filter_by(student_id=student.id)
            
            if start_date_obj:
                absences_query = absences_query.filter(
                    Absence.date >= start_date_obj.date(),
                    Absence.date <= end_date_obj.date()
                )
            
            absences_count = absences_query.count()
            total_absences += absences_count
            
            preview_data.append({
                'name': student.full_name,
                'group': student.group.name if student.group else '',
                'misses': absences_count,
                'phone': student.phone or ''
            })
        
        # Статистика групп
        groups_count = query.with_entities(Student.group_id).distinct().count()
        
        return jsonify({
            'success': True,
            'students': preview_data,
            'count': total_count,
            'groups_count': groups_count,
            'stats': {
                'groups_count': groups_count,
                'students_count': total_count,
                'absences_count': total_absences
            },
            'has_data': total_count > 0,
            'period': period,
            'start_date': start_date_obj.strftime('%Y-%m-%d') if start_date_obj else None,
            'end_date': end_date_obj.strftime('%Y-%m-%d')
        })
    except Exception as e:
        logging.error(f"Preview error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False, 
            'error': str(e),
            'students': [],
            'count': 0,
            'groups_count': 0,
            'stats': {
                'groups_count': 0,
                'students_count': 0,
                'absences_count': 0
            },
            'has_data': False
        })

# =============================================
# СТАРЫЙ ЭКСПОРТ (для совместимости)
# =============================================

@dashboard_bp.route('/export_students')
@login_required
def export_students():
    """Простой экспорт списка студентов в CSV (старый вариант)"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    students = Student.query.all()
    
    # Создаем CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    # Заголовки
    writer.writerow(['ID', 'ФИО', 'Группа', 'Телефон', 'Куратор', 'Староста'])
    
    # Данные
    for student in students:
        group_name = student.group.name if student.group else ''
        curator_name = student.group.curator.full_name if student.group and student.group.curator else ''
        leader_name = student.group.leader.full_name if student.group and student.group.leader else ''
        
        writer.writerow([
            student.id,
            student.full_name,
            group_name,
            student.phone or '',
            curator_name,
            leader_name
        ])
    
    # Логируем действие
    audit_log = AuditLog(
        user_id=current_user.id,
        action='export_students',
        description=f'Экспорт списка студентов ({len(students)} записей)',
        ip_address=request.remote_addr
    )
    db.session.add(audit_log)
    db.session.commit()
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'students_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

# =============================================
# ЭКСПОРТ ПОЛЬЗОВАТЕЛЕЙ (кураторов/старост)
# =============================================

@dashboard_bp.route('/export-users')
@login_required
def export_users_route():
    """Экспорт списка кураторов и старост"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    try:
        # Получаем всех кураторов и старостов
        users = User.query.filter(User.role.in_(['curator', 'leader'])).all()
        
        # Подготавливаем данные
        data = []
        for user in users:
            # Получаем информацию о группах
            groups_info = []
            if user.role == 'curator':
                groups = Group.query.filter_by(curator_id=user.id).all()
                groups_info = [g.name for g in groups]
            elif user.role == 'leader':
                group = Group.query.filter_by(leader_id=user.id).first()
                groups_info = [group.name] if group else []
            
            data.append({
                'ID': user.id,
                'ФИО': user.full_name,
                'Роль': 'Куратор' if user.role == 'curator' else 'Староста',
                'Телефон': user.phone or '',
                'Telegram': user.telegram or '',
                'Email': user.email or '',
                'Группы': ', '.join(groups_info),
                'Статус': 'Подтверждён' if user.is_confirmed else ('Отклонён' if user.is_rejected else 'Ожидает'),
                'Дата регистрации': user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else '',
                'Подтверждён': 'Да' if user.is_confirmed else 'Нет'
            })
        
        # Создаем DataFrame
        df = pd.DataFrame(data)
        
        # Создаем Excel файл в памяти
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Кураторы и старосты', index=False)
            
            # Автонастройка ширины колонок
            worksheet = writer.sheets['Кураторы и старосты']
            for column in df:
                column_width = max(df[column].astype(str).map(len).max(), len(column))
                col_idx = df.columns.get_loc(column)
                worksheet.column_dimensions[chr(65 + col_idx)].width = min(column_width + 2, 50)
        
        output.seek(0)
        
        # Логируем действие
        audit_log = AuditLog(
            user_id=current_user.id,
            action='export_users',
            description=f'Экспорт кураторов и старостов ({len(users)} записей)',
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        filename = f'users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return send_file(output,
                       download_name=filename,
                       as_attachment=True,
                       mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
    except Exception as e:
        logging.error(f"Error exporting users: {str(e)}")
        flash(f'Ошибка при экспорте пользователей: {str(e)}', 'danger')
        return redirect(url_for('dashboard.admin_dashboard'))

# =============================================
# ИМПОРТ СТУДЕНТОВ
# =============================================

@dashboard_bp.route('/import_students', methods=['GET', 'POST'])
@login_required
def import_students():
    """Импорт студентов из файла"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        file = request.files.get('file')
        
        if not file or file.filename == '':
            flash('Выберите файл', 'danger')
            return redirect(url_for('dashboard.import_students'))
        
        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file, delimiter=';')
            elif file.filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
            else:
                flash('Поддерживаются только CSV и Excel файлы', 'danger')
                return redirect(url_for('dashboard.import_students'))
            
            # Проверяем необходимые колонки
            required_columns = ['ФИО', 'Группа']
            for col in required_columns:
                if col not in df.columns:
                    flash(f'Файл должен содержать колонку "{col}"', 'danger')
                    return redirect(url_for('dashboard.import_students'))
            
            imported_count = 0
            errors = []
            
            for index, row in df.iterrows():
                try:
                    full_name = str(row['ФИО']).strip()
                    group_name = str(row['Группа']).strip()
                    
                    if not full_name:
                        continue
                    
                    # Ищем группу по имени
                    group = Group.query.filter_by(name=group_name).first()
                    if not group:
                        errors.append(f'Строка {index + 2}: Группа "{group_name}" не найдена')
                        continue
                    
                    # Создаем студента
                    student = Student(
                        full_name=full_name,
                        group_id=group.id,
                        phone=str(row['Телефон']).strip() if 'Телефон' in df.columns and pd.notna(row['Телефон']) else None
                    )
                    db.session.add(student)
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f'Строка {index + 2}: {str(e)}')
            
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='import_students',
                description=f'Импортировано {imported_count} студентов',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            if errors:
                flash(f'Импортировано {imported_count} студентов. Ошибок: {len(errors)}', 'warning')
            else:
                flash(f'Успешно импортировано {imported_count} студентов', 'success')
                
            return redirect(url_for('dashboard.students'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обработке файла: {str(e)}', 'danger')
    
    return render_template('import_students.html')

# =============================================
# ИМПОРТ ПОЛЬЗОВАТЕЛЕЙ
# =============================================

@dashboard_bp.route('/import-users', methods=['GET', 'POST'])
@login_required
def import_users_route():
    """Импорт кураторов и старостов из файла"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        file = request.files.get('file')
        
        if not file or file.filename == '':
            flash('Выберите файл', 'danger')
            return redirect(url_for('dashboard.import_users_route'))
        
        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file, delimiter=';')
            elif file.filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
            else:
                flash('Поддерживаются только CSV и Excel файлы', 'danger')
                return redirect(url_for('dashboard.import_users_route'))
            
            # Проверяем необходимые колонки
            required_columns = ['ФИО', 'Роль', 'Телефон', 'Пароль']
            for col in required_columns:
                if col not in df.columns:
                    flash(f'Файл должен содержать колонку "{col}"', 'danger')
                    return redirect(url_for('dashboard.import_users_route'))
            
            imported_count = 0
            errors = []
            
            for index, row in df.iterrows():
                try:
                    full_name = str(row['ФИО']).strip()
                    role = str(row['Роль']).strip().lower()
                    phone = str(row['Телефон']).strip()
                    password = str(row['Пароль']).strip()
                    
                    if not all([full_name, role, phone, password]):
                        errors.append(f'Строка {index + 2}: Не все обязательные поля заполнены')
                        continue
                    
                    # Проверяем роль
                    if role not in ['куратор', 'староста', 'curator', 'leader']:
                        errors.append(f'Строка {index + 2}: Неверная роль "{role}"')
                        continue
                    
                    # Проверяем уникальность телефона
                    existing_user = User.query.filter_by(phone=phone).first()
                    if existing_user:
                        errors.append(f'Строка {index + 2}: Пользователь с телефоном {phone} уже существует')
                        continue
                    
                    # Определяем роль для базы данных
                    db_role = 'curator' if role in ['куратор', 'curator'] else 'leader'
                    
                    # Создаем пользователя
                    user = User(
                        full_name=full_name,
                        phone=phone,
                        telegram=str(row['Telegram']).strip() if 'Telegram' in df.columns and pd.notna(row['Telegram']) else None,
                        email=str(row['Email']).strip() if 'Email' in df.columns and pd.notna(row['Email']) else None,
                        role=db_role,
                        password=bcrypt.generate_password_hash(password).decode('utf-8'),
                        is_confirmed=True  # При импорте сразу подтверждаем
                    )
                    
                    db.session.add(user)
                    db.session.flush()  # Получаем ID пользователя
                    
                    # Обрабатываем группы для кураторов
                    if db_role == 'curator' and 'Группы' in df.columns and pd.notna(row['Группы']):
                        group_names = [g.strip() for g in str(row['Группы']).split(',')]
                        for group_name in group_names:
                            if group_name:
                                group = Group.query.filter_by(name=group_name).first()
                                if group:
                                    group.curator_id = user.id
                                else:
                                    errors.append(f'Строка {index + 2}: Группа "{group_name}" не найдена')
                    
                    # Обрабатываем группу для старост
                    elif db_role == 'leader' and 'Группа' in df.columns and pd.notna(row['Группа']):
                        group_name = str(row['Группа']).strip()
                        group = Group.query.filter_by(name=group_name).first()
                        if group:
                            # Проверяем, нет ли уже старосты в группе
                            if group.leader_id:
                                errors.append(f'Строка {index + 2}: В группе "{group_name}" уже есть староста')
                            else:
                                group.leader_id = user.id
                        else:
                            errors.append(f'Строка {index + 2}: Группа "{group_name}" не найдена')
                    
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f'Строка {index + 2}: {str(e)}')
            
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='import_users',
                description=f'Импортировано {imported_count} пользователей',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            if errors:
                flash(f'Импортировано {imported_count} пользователей. Ошибок: {len(errors)}', 'warning')
            else:
                flash(f'Успешно импортировано {imported_count} пользователей', 'success')
                
            return redirect(url_for('dashboard.admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обработке файла: {str(e)}', 'danger')
    
    return render_template('import_users.html')

# =============================================
# СПИСОК ПОЛЬЗОВАТЕЛЕЙ - ИСПРАВЛЕННАЯ ВЕРСИЯ
# =============================================

@dashboard_bp.route('/users-list')
@login_required
def users_list():
    """Список всех кураторов и старост с группировкой по группам"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Получаем все группы с кураторами и старостами
    groups = Group.query.order_by(Group.name).all()
    
    # Собираем данные в удобном формате для отображения
    grouped_data = {}
    
    for group in groups:
        # Получаем куратора группы
        curator = group.curator
        curator_groups = []
        
        # Если есть куратор, получаем все его группы
        if curator:
            curator_groups = [g.name for g in curator.get_curator_groups()] if hasattr(curator, 'get_curator_groups') else []
        
        # Получаем старосту группы
        leader = group.leader
        
        # Формируем данные для группы
        grouped_data[group.name] = {
            'curator': curator,
            'leader': leader,
            'curator_groups': curator_groups if curator_groups else [group.name]
        }
    
    return render_template('users_list.html', 
                         grouped_data=grouped_data,
                         groups_count=len(groups))

# =============================================
# УПРАВЛЕНИЕ ГРУППАМИ
# =============================================

@dashboard_bp.route('/manage-groups')
@login_required
def manage_groups():
    """Страница управления группами"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    groups = Group.query.all()
    return render_template('manage_groups.html', groups=groups)

# =============================================
# УПРАВЛЕНИЕ СТУДЕНТАМИ
# =============================================

@dashboard_bp.route('/manage-students')
@login_required
def manage_students():
    """Страница управления студентами"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    students = Student.query.all()
    groups = Group.query.all()
    
    return render_template('manage_students.html', students=students, groups=groups)

# =============================================
# СТАТИСТИКА СИСТЕМЫ
# =============================================

@dashboard_bp.route('/system-stats')
@login_required
def system_stats():
    """Статистика системы"""
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Базовая статистика
    total_students = Student.query.count()
    total_groups = Group.query.count()
    total_users = User.query.count()
    total_absences = Absence.query.count()
    
    # Статистика по ролям
    admin_count = User.query.filter_by(role='admin').count()
    curator_count = User.query.filter_by(role='curator', is_confirmed=True).count()
    leader_count = User.query.filter_by(role='leader', is_confirmed=True).count()
    
    # Статистика по статусам
    pending_users = User.query.filter_by(is_confirmed=False, is_rejected=False).count()
    rejected_users = User.query.filter_by(is_rejected=True).count()
    
    # Статистика за сегодня
    today = datetime.now().date()
    today_absences = Absence.query.filter(Absence.date == today).count()
    
    # Статистика за неделю
    week_ago = today - timedelta(days=7)
    week_absences = Absence.query.filter(Absence.date >= week_ago, Absence.date <= today).count()
    
    # Статистика по группам
    groups_stats = []
    groups = Group.query.all()
    for group in groups:
        student_count = Student.query.filter_by(group_id=group.id).count()
        absence_count = Absence.query.join(Student).filter(Student.group_id == group.id).count()
        groups_stats.append({
            'name': group.name,
            'student_count': student_count,
            'absence_count': absence_count,
            'curator': group.curator.full_name if group.curator else 'Не назначен',
            'leader': group.leader.full_name if group.leader else 'Не назначен'
        })
    
    return render_template('system_stats.html',
                         total_students=total_students,
                         total_groups=total_groups,
                         total_users=total_users,
                         total_absences=total_absences,
                         admin_count=admin_count,
                         curator_count=curator_count,
                         leader_count=leader_count,
                         pending_users=pending_users,
                         rejected_users=rejected_users,
                         today_absences=today_absences,
                         week_absences=week_absences,
                         groups_stats=groups_stats)

# =============================================
# УПРАВЛЕНИЕ СТУДЕНТАМИ
# =============================================

@dashboard_bp.route('/students')
@login_required
def students():
    # Проверяем права доступа
    if current_user.role not in ['admin', 'curator', 'leader']:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Получаем список студентов с учётом роли
    students_list = get_user_students(current_user)
    
    groups = get_user_groups(current_user)  # Только доступные группы
    return render_template('students_list.html', students=students_list, groups=groups)

@dashboard_bp.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    # Проверяем права доступа
    if current_user.role not in ['admin', 'curator']:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    groups = get_user_groups(current_user)
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        group_id = request.form.get('group_id')
        phone = request.form.get('phone')
        
        if not full_name:
            flash('ФИО обязательно для заполнения', 'danger')
            return redirect(url_for('dashboard.add_student'))
        
        # Проверяем, доступна ли группа пользователю
        group_ids = [g.id for g in groups]
        if group_id and int(group_id) not in group_ids:
            flash('Выбранная группа недоступна', 'danger')
            return redirect(url_for('dashboard.add_student'))
        
        new_student = Student(
            full_name=full_name,
            group_id=int(group_id) if group_id else None,
            phone=phone or None
        )
        
        try:
            db.session.add(new_student)
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='add_student',
                description=f'Добавлен студент: {full_name}',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            flash(f'Студент {full_name} успешно добавлен', 'success')
            return redirect(url_for('dashboard.students'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении студента: {str(e)}', 'danger')
    
    return render_template('student_form.html', action='add', groups=groups)

@dashboard_bp.route('/students/edit/<int:student_id>', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    # Проверяем права доступа
    if current_user.role not in ['admin', 'curator']:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    student = Student.query.get_or_404(student_id)
    
    # Проверяем, имеет ли пользователь доступ к этому студенту
    user_students = get_user_students(current_user)
    student_ids = [s.id for s in user_students]
    if student.id not in student_ids:
        flash('Нет прав для редактирования этого студента', 'danger')
        return redirect(url_for('dashboard.students'))
    
    groups = get_user_groups(current_user)
    
    if request.method == 'POST':
        student.full_name = request.form.get('full_name')
        group_id = request.form.get('group_id')
        
        # Проверяем, доступна ли группа пользователю
        group_ids = [g.id for g in groups]
        if group_id and int(group_id) not in group_ids:
            flash('Выбранная группа недоступна', 'danger')
            return redirect(url_for('dashboard.edit_student', student_id=student_id))
        
        student.group_id = int(group_id) if group_id else None
        student.phone = request.form.get('phone')
        
        try:
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='edit_student',
                description=f'Изменён студент: {student.full_name} (ID: {student_id})',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            flash('Студент успешно обновлён', 'success')
            return redirect(url_for('dashboard.students'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении студента: {str(e)}', 'danger')
    
    return render_template('student_form.html', action='edit', student=student, groups=groups)

@dashboard_bp.route('/students/delete/<int:student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    # Проверяем права доступа
    if current_user.role not in ['admin', 'curator']:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    student = Student.query.get_or_404(student_id)
    
    # Проверяем, имеет ли пользователь доступ к этому студенту
    user_students = get_user_students(current_user)
    student_ids = [s.id for s in user_students]
    if student.id not in student_ids:
        flash('Нет прав для удаления этого студента', 'danger')
        return redirect(url_for('dashboard.students'))
    
    student_name = student.full_name
    
    try:
        # Удаляем связанные пропуски
        Absence.query.filter_by(student_id=student_id).delete()
        
        db.session.delete(student)
        db.session.commit()
        
        # Логируем действие
        audit_log = AuditLog(
            user_id=current_user.id,
            action='delete_student',
            description=f'Удалён студент: {student_name} (ID: {student_id})',
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        flash(f'Студент {student_name} успешно удалён', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении студента: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.students'))

@dashboard_bp.route('/upload_students', methods=['GET', 'POST'])
@login_required
def upload_students():
    if current_user.role not in ['admin', 'curator']:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    groups = get_user_groups(current_user)
    
    if request.method == 'POST':
        group_id = request.form.get('group_id')
        file = request.files.get('file')
        
        if not group_id:
            flash('Выберите группу', 'danger')
            return redirect(url_for('dashboard.upload_students'))
        
        # Проверяем, доступна ли группа пользователю
        group_ids = [g.id for g in groups]
        if int(group_id) not in group_ids:
            flash('Выбранная группа недоступна', 'danger')
            return redirect(url_for('dashboard.upload_students'))
        
        if not file or file.filename == '':
            flash('Выберите файл', 'danger')
            return redirect(url_for('dashboard.upload_students'))
        
        try:
            # Обработка CSV
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file)
            # Обработка Excel
            elif file.filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
            else:
                flash('Поддерживаются только CSV и Excel файлы', 'danger')
                return redirect(url_for('dashboard.upload_students'))
            
            # Проверяем наличие колонки с ФИО
            if 'ФИО' not in df.columns and 'full_name' not in df.columns:
                flash('Файл должен содержать колонку "ФИО" или "full_name"', 'danger')
                return redirect(url_for('dashboard.upload_students'))
            
            added_count = 0
            errors = []
            
            for index, row in df.iterrows():
                try:
                    # Ищем колонку с ФИО
                    if 'ФИО' in df.columns:
                        full_name = row['ФИО']
                    else:
                        full_name = row['full_name']
                    
                    # Пропускаем пустые строки
                    if pd.isna(full_name):
                        continue
                    
                    # Создаем студента
                    student = Student(
                        full_name=str(full_name).strip(),
                        group_id=int(group_id)
                    )
                    db.session.add(student)
                    added_count += 1
                    
                except Exception as e:
                    errors.append(f'Строка {index + 2}: {str(e)}')
            
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='upload_students',
                description=f'Импортировано {added_count} студентов в группу ID: {group_id}',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            if errors:
                flash(f'Добавлено {added_count} студентов. Ошибок: {len(errors)}', 'warning')
            else:
                flash(f'Успешно добавлено {added_count} студентов', 'success')
                
            return redirect(url_for('dashboard.students'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обработке файла: {str(e)}', 'danger')
    
    return render_template('upload_students.html', groups=groups)

# =============================================
# УПРАВЛЕНИЕ ГРУППАМИ
# =============================================

@dashboard_bp.route('/groups')
@login_required
def groups_list():
    # ДОСТУП ТОЛЬКО ДЛЯ АДМИНОВ (как и для добавления групп)
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    groups = Group.query.all()
    return render_template('groups_list.html', groups=groups)

@dashboard_bp.route('/groups/add', methods=['GET', 'POST'])
@login_required
def add_group():
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    curators = User.query.filter_by(role='curator', is_confirmed=True).all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        curator_id = request.form.get('curator_id')
        
        if not name:
            flash('Название группы обязательно', 'danger')
            return redirect(url_for('dashboard.add_group'))
        
        # Проверяем уникальность названия группы
        existing_group = Group.query.filter_by(name=name).first()
        if existing_group:
            flash('Группа с таким названием уже существует', 'danger')
            return redirect(url_for('dashboard.add_group'))
        
        new_group = Group(
            name=name,
            curator_id=int(curator_id) if curator_id else None
        )
        
        try:
            db.session.add(new_group)
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='add_group',
                description=f'Добавлена группа: {name}',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            flash(f'Группа {name} успешно добавлена', 'success')
            return redirect(url_for('dashboard.groups_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении группы: {str(e)}', 'danger')
    
    return render_template('group_form.html', action='add', curators=curators)

@dashboard_bp.route('/groups/edit/<int:group_id>', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    group = Group.query.get_or_404(group_id)
    curators = User.query.filter_by(role='curator', is_confirmed=True).all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        curator_id = request.form.get('curator_id')
        
        # Проверяем уникальность названия (исключая текущую группу)
        existing_group = Group.query.filter(Group.name == name, Group.id != group_id).first()
        if existing_group:
            flash('Группа с таким названием уже существует', 'danger')
            return redirect(url_for('dashboard.edit_group', group_id=group_id))
        
        group.name = name
        group.curator_id = int(curator_id) if curator_id else None
        
        try:
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='edit_group',
                description=f'Изменена группа: {group.name} (ID: {group_id})',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            flash('Группа успешно обновлена', 'success')
            return redirect(url_for('dashboard.groups_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении группы: {str(e)}', 'danger')
    
    return render_template('group_form.html', action='edit', group=group, curators=curators)

@dashboard_bp.route('/groups/delete/<int:group_id>', methods=['POST'])
@login_required
def delete_group(group_id):
    if current_user.role != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('dashboard.index'))
    
    group = Group.query.get_or_404(group_id)
    group_name = group.name
    
    try:
        # Удаляем связанных студентов
        Student.query.filter_by(group_id=group_id).delete()
        
        db.session.delete(group)
        db.session.commit()
        
        # Логируем действие
        audit_log = AuditLog(
            user_id=current_user.id,
            action='delete_group',
            description=f'Удалена группа: {group_name} (ID: {group_id})',
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        flash(f'Группа {group_name} успешно удалена', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении группы: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.groups_list'))

# =============================================
# УПРАВЛЕНИЕ ПРОПУСКАМИ
# =============================================

@dashboard_bp.route('/absences')
@login_required
def absences_list():
    # Получаем пропуски в зависимости от роли
    absences_list = get_user_absences(current_user)
    
    return render_template('absences.html', absences=absences_list)

@dashboard_bp.route('/absences/add', methods=['GET', 'POST'])
@login_required
def add_absence():
    # Получаем студентов в зависимости от роли
    students = get_user_students(current_user)
    
    if not students:
        flash('Нет доступных студентов для добавления пропусков', 'warning')
        return redirect(url_for('dashboard.absences_list'))
    
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        date_str = request.form.get('date')
        reason = request.form.get('reason')
        lessons_count = request.form.get('lessons_count', 1)
        
        if not student_id or not date_str:
            flash('Заполните обязательные поля', 'danger')
            return redirect(url_for('dashboard.add_absence'))
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M') if 'T' in date_str else datetime.strptime(date_str, '%Y-%m-%d')
            
            # Проверяем, принадлежит ли студент доступным пользователю
            student = Student.query.get(int(student_id))
            user_students = get_user_students(current_user)
            student_ids = [s.id for s in user_students]
            
            if student.id not in student_ids:
                flash('Нет прав для добавления пропуска этому студенту', 'danger')
                return redirect(url_for('dashboard.add_absence'))
            
            new_absence = Absence(
                student_id=int(student_id),
                date=date,
                reason=reason,
                lessons_count=int(lessons_count)
            )
            
            db.session.add(new_absence)
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='add_absence',
                description=f'Добавлен пропуск для студента ID: {student_id} на {date_str}',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            flash('Пропуск успешно добавлен', 'success')
            return redirect(url_for('dashboard.absences_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении пропуска: {str(e)}', 'danger')
    
    return render_template('add_absence.html', students=students)

@dashboard_bp.route('/absences/edit/<int:absence_id>', methods=['GET', 'POST'])
@login_required
def edit_absence(absence_id):
    absence = Absence.query.get_or_404(absence_id)
    
    # Проверяем права
    if current_user.role == 'admin':
        pass  # Админ может всё
    elif current_user.role == 'curator':
        # Проверяем, принадлежит ли студент группе куратора
        student = Student.query.get(absence.student_id)
        group = Group.query.get(student.group_id) if student else None
        if not group or group.curator_id != current_user.id:
            flash('Нет прав для редактирования этого пропуска', 'danger')
            return redirect(url_for('dashboard.absences_list'))
    else:  # leader
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('dashboard.absences_list'))
    
    # Получаем список студентов для выпадающего списка
    students = get_user_students(current_user)
    
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        date_str = request.form.get('date')
        reason = request.form.get('reason')
        lessons_count = request.form.get('lessons_count', 1)
        
        if not student_id or not date_str:
            flash('Заполните обязательные поля', 'danger')
            return redirect(url_for('dashboard.edit_absence', absence_id=absence_id))
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d') if 'T' not in date_str else datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
            
            # Проверяем, принадлежит ли студент доступным пользователю
            user_students = get_user_students(current_user)
            student_ids = [s.id for s in user_students]
            if int(student_id) not in student_ids:
                flash('Нет прав для редактирования пропуска этого студента', 'danger')
                return redirect(url_for('dashboard.edit_absence', absence_id=absence_id))
            
            absence.student_id = int(student_id)
            absence.date = date
            absence.reason = reason
            absence.lessons_count = int(lessons_count)
            
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='edit_absence',
                description=f'Отредактирован пропуск ID: {absence_id}',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            flash('Пропуск успешно обновлён', 'success')
            return redirect(url_for('dashboard.absences_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении пропуска: {str(e)}', 'danger')
    
    # Для GET запроса показываем форму редактирования
    return render_template('edit_absence.html', 
                         absence=absence, 
                         students=students,
                         today=datetime.now().strftime('%Y-%m-%d'))

@dashboard_bp.route('/absences/delete/<int:absence_id>', methods=['POST'])
@login_required
def delete_absence(absence_id):
    absence = Absence.query.get_or_404(absence_id)
    
    # Проверяем права
    if current_user.role == 'admin':
        pass  # Админ может всё
    elif current_user.role == 'curator':
        # Проверяем, принадлежит ли студент группе куратора
        student = Student.query.get(absence.student_id)
        group = Group.query.get(student.group_id) if student else None
        if not group or group.curator_id != current_user.id:
            flash('Нет прав для удаления этого пропуска', 'danger')
            return redirect(url_for('dashboard.absences_list'))
    else:  # leader
        flash('Недостаточно прав', 'danger')
        return redirect(url_for('dashboard.absences_list'))
    
    try:
        db.session.delete(absence)
        db.session.commit()
        
        # Логируем действие
        audit_log = AuditLog(
            user_id=current_user.id,
            action='delete_absence',
            description=f'Удалён пропуск ID: {absence_id}',
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        flash('Пропуск успешно удалён', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении пропуска: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.absences_list'))

# =============================================
# АНАЛИТИКА
# =============================================

@dashboard_bp.route('/student_analytics')
@login_required
def student_analytics():
    # Получаем данные в зависимости от роли
    students_data = get_user_students(current_user)
    
    # Получаем кураторов и старост
    if current_user.role == 'admin':
        curators = User.query.filter_by(role='curator', is_confirmed=True).all()
        leaders = User.query.filter_by(role='leader', is_confirmed=True).all()
    elif current_user.role == 'curator':
        curators = [current_user]
        leaders = User.query.filter_by(role='leader', is_confirmed=True).all()
    else:  # leader
        curators = User.query.filter_by(role='curator', is_confirmed=True).all()
        leaders = [current_user]
    
    # Собираем статистику
    student_stats = []
    for student in students_data:
        absences = Absence.query.filter_by(student_id=student.id).all()
        total_absences = len(absences)
        excused = sum(1 for a in absences if a.reason and a.reason.lower() in ['болезнь', 'справка', 'уважительная', 'по болезни', 'мед. справка'])
        unexcused = total_absences - excused
        
        student_stats.append({
            'student_name': student.full_name,
            'group_name': student.group.name if student.group else '-',
            'curator_name': student.group.curator.full_name if student.group and student.group.curator else '-',
            'leader_name': student.group.leader.full_name if student.group and student.group.leader else '-',
            'total_absences': total_absences,
            'excused': excused,
            'unexcused': unexcused
        })
    
    return render_template('student_analytics.html', 
                         student_data=student_stats,
                         curators=curators,
                         leaders=leaders,
                         user=current_user)

@dashboard_bp.route('/group_analytics', methods=['GET', 'POST'])
@login_required
def group_analytics():
    # Получаем доступные группы в зависимости от роли
    groups = get_user_groups(current_user)
    
    selected_group = None
    absences_data = None
    student_stats = []
    
    if request.method == 'POST':
        group_id = request.form.get('group_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        
        if group_id:
            # Проверяем, доступна ли группа пользователю
            group_ids = [g.id for g in groups]
            if int(group_id) not in group_ids:
                flash('Выбранная группа недоступна', 'danger')
                return redirect(url_for('dashboard.group_analytics'))
            
            selected_group = Group.query.get(int(group_id))
            
            if selected_group:
                try:
                    start = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else datetime.now().date() - timedelta(days=30)
                    end = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else datetime.now().date()
                    
                    # Получаем всех студентов группы
                    students = Student.query.filter_by(group_id=selected_group.id).all()
                    
                    total_excused = 0
                    total_unexcused = 0
                    
                    for student in students:
                        # Пропуски студента за период
                        absences = Absence.query.filter(
                            Absence.student_id == student.id,
                            Absence.date >= start,
                            Absence.date <= end
                        ).all()
                        
                        total = len(absences)
                        excused = sum(1 for a in absences if a.reason and a.reason.lower() in ['болезнь', 'справка', 'уважительная', 'по болезни', 'мед. справка'])
                        unexcused = total - excused
                        
                        if total > 0:  # Добавляем только студентов с пропусками
                            student_stats.append({
                                'student': student.full_name,
                                'total': total,
                                'excused': excused,
                                'unexcused': unexcused
                            })
                        
                        total_excused += excused
                        total_unexcused += unexcused
                    
                    absences_data = {
                        'total': total_excused + total_unexcused,
                        'total_excused': total_excused,
                        'total_unexcused': total_unexcused
                    }
                    
                except Exception as e:
                    flash(f'Ошибка обработки дат: {str(e)}', 'danger')
    
    return render_template('group_analytics.html',
                         groups=groups,
                         selected_group=selected_group,
                         absences_data=absences_data,
                         student_stats=student_stats)

# =============================================
# НАСТРОЙКИ ПРОФИЛЯ
# =============================================

@dashboard_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Используем current_user напрямую (уже загружен Flask-Login)
    user = current_user
    
    if request.method == 'POST':
        # Обновление данных
        user.full_name = request.form.get('full_name')
        user.phone = request.form.get('phone')
        user.email = request.form.get('email')
        user.telegram = request.form.get('telegram')
        
        # Обработка смены пароля
        current_password = request.form.get('current_password')
        new_password = request.form.get('password')
        
        if current_password and new_password:
            # Проверяем текущий пароль
            if not user.check_password(current_password):
                flash('Неверный текущий пароль', 'danger')
                return redirect(url_for('dashboard.settings'))
            
            # Проверяем совпадение паролей
            if new_password != request.form.get('confirm_password'):
                flash('Новые пароли не совпадают', 'danger')
                return redirect(url_for('dashboard.settings'))
            
            # Устанавливаем новый пароль
            user.set_password(new_password)
            flash('Пароль успешно изменен', 'success')
        
        try:
            db.session.commit()
            
            # Логируем действие
            audit_log = AuditLog(
                user_id=current_user.id,
                action='update_settings',
                description='Обновлены настройки профиля',
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            flash('Настройки профиля обновлены', 'success')
            return redirect(url_for('dashboard.settings'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка обновления настроек: {str(e)}', 'danger')
            return redirect(url_for('dashboard.settings'))
    
    # GET запрос - просто показываем страницу настроек
    return render_template('settings.html', user=user)

# =============================================
# API для аналитики
# =============================================

@dashboard_bp.route('/api/student-analytics')
@login_required
def api_student_analytics():
    # Получаем параметры фильтрации
    student_name = request.args.get('student_name', '').strip()
    group_name = request.args.get('group_name', '').strip()
    curator_id = request.args.get('curator_id')
    leader_id = request.args.get('leader_id')
    
    # Начинаем запрос с доступных пользователю студентов
    students = get_user_students(current_user)
    
    # Применяем фильтры
    filtered_students = []
    for student in students:
        include = True
        
        if student_name and student_name.lower() not in student.full_name.lower():
            include = False
        
        if group_name and (not student.group or group_name.lower() not in student.group.name.lower()):
            include = False
        
        if curator_id and (not student.group or str(student.group.curator_id) != curator_id):
            include = False
        
        if leader_id and (not student.group or str(student.group.leader_id) != leader_id):
            include = False
        
        if include:
            filtered_students.append(student)
    
    # Собираем статистику
    result = []
    for student in filtered_students:
        absences = Absence.query.filter_by(student_id=student.id).all()
        total = len(absences)
        excused = sum(1 for a in absences if a.reason and a.reason.lower() in ['болезнь', 'справка', 'уважительная', 'по болезни', 'мед. справка'])
        unexcused = total - excused
    
        result.append({
            'student_name': student.full_name,
            'group_name': student.group.name if student.group else '-',
            'curator_name': student.group.curator.full_name if student.group and student.group.curator else '-',
            'leader_name': student.group.leader.full_name if student.group and student.group.leader else '-',
            'total_absences': total,
            'excused': excused,
            'unexcused': unexcused
        })
    
    return jsonify(result)

@dashboard_bp.route('/api/group-analytics')
@login_required
def api_group_analytics():
    period = request.args.get('period', 'week')
    group_id = request.args.get('group_id')
    
    if not group_id:
        return jsonify({'error': 'group_id is required'}), 400
    
    try:
        # Получаем группу
        group = Group.query.get(group_id)
        if not group:
            return jsonify({'error': 'Group not found'}), 404
        
        # Определяем период
        end_date = datetime.now().date()
        if period == 'week':
            start_date = end_date - timedelta(days=7)
        elif period == 'month':
            start_date = end_date - timedelta(days=30)
        elif period == 'semester':
            start_date = end_date - timedelta(days=180)
        elif period == 'year':
            start_date = end_date - timedelta(days=365)
        else:
            start_date = end_date - timedelta(days=7)
        
        # Получаем статистику
        absences = Absence.query.join(Student).filter(
            Student.group_id == group_id,
            Absence.date >= start_date,
            Absence.date <= end_date
        ).all()
        
        total = len(absences)
        excused = sum(1 for a in absences if a.reason and a.reason.lower() in ['болезнь', 'справка', 'уважительная', 'по болезни', 'мед. справка'])
        unexcused = total - excused
        
        # Статистика по дням
        daily_stats = {}
        for absence in absences:
            date_str = absence.date.strftime('%Y-%m-%d')
            if date_str not in daily_stats:
                daily_stats[date_str] = 0
            daily_stats[date_str] += 1
        
        return jsonify({
            'total': total,
            'excused': excused,
            'unexcused': unexcused,
            'daily_stats': daily_stats,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# =============================================
# ДОПОЛНИТЕЛЬНЫЙ API ДЛЯ ПРЕДПРОСМОТРА ЭКСПОРТА
# =============================================

@dashboard_bp.route('/api/export-preview-data')
@login_required
def export_preview_data():
    """API для предварительного просмотра данных (реальные данные из БД) - ДУБЛИРУЮЩИЙ МЕТОД"""
    # Проверяем права доступа - возвращаем JSON, а не редирект
    if current_user.role != 'admin':
        return jsonify({
            'success': False, 
            'error': 'Доступ запрещен. Требуется роль администратора.',
            'students': [],
            'count': 0,
            'groups_count': 0,
            'stats': {
                'groups_count': 0,
                'students_count': 0,
                'absences_count': 0
            },
            'has_data': False
        }), 403
    
    try:
        # Получаем параметры из запроса
        group_id = request.args.get('group_id')
        curator_id = request.args.get('curator_id')
        headman_id = request.args.get('headman_id')  # Новый параметр
        period = request.args.get('period', 'week')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        include_stats = request.args.get('include_stats', 'false') == 'true'
        
        # Определяем период
        end_date_obj = datetime.now()
        start_date_obj = None
        
        if period != 'all':
            if period == 'week':
                start_date_obj = end_date_obj - timedelta(days=7)
            elif period == 'month':
                start_date_obj = end_date_obj - timedelta(days=30)
            elif period == 'semester':
                start_date_obj = end_date_obj - timedelta(days=180)
            elif period == 'year':
                start_date_obj = end_date_obj - timedelta(days=365)
            elif period == 'custom' and start_date and end_date:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            else:
                start_date_obj = end_date_obj - timedelta(days=7)
        
        query = Student.query
        
        if group_id and group_id != '':
            query = query.filter_by(group_id=group_id)
        
        if curator_id and curator_id != '':
            curator_groups = Group.query.filter_by(curator_id=curator_id).all()
            if curator_groups:
                curator_group_ids = [g.id for g in curator_groups]
                query = query.filter(Student.group_id.in_(curator_group_ids))
        
        # ДОБАВЛЯЕМ ФИЛЬТР ПО СТАРОСТЕ
        if headman_id and headman_id != '':
            leader_group = Group.query.filter_by(leader_id=headman_id).first()
            if leader_group:
                query = query.filter_by(group_id=leader_group.id)
        
        # Получаем реальные данные
        total_count = query.count()
        students = query.limit(10).all()
        
        preview_data = []
        total_absences = 0
        
        for student in students:
            # Считаем пропуски
            absences_query = Absence.query.filter_by(student_id=student.id)
            
            if start_date_obj:
                absences_query = absences_query.filter(
                    Absence.date >= start_date_obj.date(),
                    Absence.date <= end_date_obj.date()
                )
            
            absences_count = absences_query.count()
            total_absences += absences_count
            
            preview_data.append({
                'name': student.full_name,
                'group': student.group.name if student.group else '',
                'misses': absences_count,
                'phone': student.phone or ''
            })
        
        # Статистика групп
        groups_count = query.with_entities(Student.group_id).distinct().count()
        
        return jsonify({
            'success': True,
            'students': preview_data,
            'count': total_count,
            'groups_count': groups_count,
            'stats': {
                'groups_count': groups_count,
                'students_count': total_count,
                'absences_count': total_absences
            },
            'has_data': total_count > 0,
            'period': period,
            'start_date': start_date_obj.strftime('%Y-%m-%d') if start_date_obj else None,
            'end_date': end_date_obj.strftime('%Y-%m-%d')
        })
    except Exception as e:
        logging.error(f"Preview error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False, 
            'error': str(e),
            'students': [],
            'count': 0,
            'groups_count': 0,
            'stats': {
                'groups_count': 0,
                'students_count': 0,
                'absences_count': 0
            },
            'has_data': False
        })