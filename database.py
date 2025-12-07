"""
ДЕМО-ВЕРСИЯ: Модуль работы с базой данных

Базовая реализация работы с SQLite.
TODO: Добавить миграции, резервное копирование, оптимизацию запросов.
"""

import aiosqlite
from datetime import datetime
from typing import List, Optional, Dict
import json

class Database:
    def __init__(self, db_path: str = "bot.db"):
        self.db_path = db_path
    
    async def init_db(self):
        """Инициализация базы данных"""
        # TODO: Добавить систему миграций для обновления схемы БД
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица участников
            await db.execute("""
                CREATE TABLE IF NOT EXISTS participants (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    registration_date TEXT,
                    current_task_id INTEGER,
                    status TEXT DEFAULT 'registered',
                    task_received_date TEXT,
                    screenshots_count INTEGER DEFAULT 0,
                    requisites TEXT,
                    FOREIGN KEY (current_task_id) REFERENCES tasks(id)
                )
            """)
            
            # Таблица заданий
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    created_date TEXT,
                    is_active INTEGER DEFAULT 1,
                    max_participants INTEGER DEFAULT 0,
                    current_participants INTEGER DEFAULT 0
                )
            """)
            
            # Таблица скриншотов
            await db.execute("""
                CREATE TABLE IF NOT EXISTS screenshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    task_id INTEGER,
                    file_id TEXT,
                    file_path TEXT,
                    upload_date TEXT,
                    FOREIGN KEY (user_id) REFERENCES participants(user_id),
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)
            
            # Таблица настроек
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            await db.commit()
    
    async def add_participant(self, user_id: int, username: str, full_name: str):
        """Добавить участника"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO participants 
                (user_id, username, full_name, registration_date, status)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, full_name, datetime.now().isoformat(), "registered"))
            await db.commit()
    
    async def get_participant(self, user_id: int) -> Optional[Dict]:
        """Получить информацию об участнике"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM participants WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def assign_task(self, user_id: int, task_id: int):
        """Назначить задание участнику"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE participants 
                SET current_task_id = ?, status = 'task_assigned', 
                    task_received_date = ?, screenshots_count = 0
                WHERE user_id = ?
            """, (task_id, datetime.now().isoformat(), user_id))
            
            await db.execute("""
                UPDATE tasks 
                SET current_participants = current_participants + 1
                WHERE id = ?
            """, (task_id,))
            
            await db.commit()
    
    async def add_task(self, description: str, max_participants: int = 0) -> int:
        """Добавить задание"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO tasks (description, created_date, max_participants)
                VALUES (?, ?, ?)
            """, (description, datetime.now().isoformat(), max_participants))
            await db.commit()
            return cursor.lastrowid
    
    async def get_all_tasks(self, active_only: bool = False) -> List[Dict]:
        """Получить все задания"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM tasks"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY id DESC"
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def delete_task(self, task_id: int):
        """Удалить задание"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE tasks SET is_active = 0 WHERE id = ?", (task_id,))
            await db.commit()
    
    async def update_task_limit(self, task_id: int, max_participants: int):
        """Обновить лимит участников для задания"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tasks 
                SET max_participants = ?
                WHERE id = ?
            """, (max_participants, task_id))
            await db.commit()
    
    async def can_assign_task(self, task_id: int) -> bool:
        """Проверить, можно ли назначить задание (лимит не исчерпан)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT max_participants, current_participants 
                FROM tasks WHERE id = ? AND is_active = 1
            """, (task_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return False
                max_p = row["max_participants"]
                current_p = row["current_participants"]
                # Если лимит = 0, то без ограничений
                return max_p == 0 or current_p < max_p
    
    async def add_screenshot(self, user_id: int, task_id: int, file_id: str, file_path: str):
        """Добавить скриншот"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO screenshots (user_id, task_id, file_id, file_path, upload_date)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, task_id, file_id, file_path, datetime.now().isoformat()))
            
            await db.execute("""
                UPDATE participants 
                SET screenshots_count = screenshots_count + 1
                WHERE user_id = ?
            """, (user_id,))
            
            await db.commit()
    
    async def get_screenshots_count(self, user_id: int) -> int:
        """Получить количество скриншотов участника"""
        participant = await self.get_participant(user_id)
        return participant["screenshots_count"] if participant else 0
    
    async def move_to_review(self, user_id: int):
        """Переместить участника в папку 'На проверку'"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE participants 
                SET status = 'pending_review'
                WHERE user_id = ?
            """, (user_id,))
            await db.commit()
    
    async def add_requisites(self, user_id: int, requisites: str):
        """Добавить реквизиты участника"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE participants 
                SET requisites = ?, status = 'pending_payment'
                WHERE user_id = ?
            """, (requisites, user_id))
            await db.commit()
    
    async def get_participants_by_status(self, status: str) -> List[Dict]:
        """Получить участников по статусу"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM participants 
                WHERE status = ?
                ORDER BY task_received_date DESC
            """, (status,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_statistics(self) -> Dict:
        """Получить статистику"""
        # TODO: Добавить кэширование статистики для производительности
        async with aiosqlite.connect(self.db_path) as db:
            stats = {}
            
            # Всего участников
            async with db.execute("SELECT COUNT(*) FROM participants") as cursor:
                stats["total_participants"] = (await cursor.fetchone())[0]
            
            # На проверку
            async with db.execute("SELECT COUNT(*) FROM participants WHERE status = 'pending_review'") as cursor:
                stats["pending_review"] = (await cursor.fetchone())[0]
            
            # На оплату
            async with db.execute("SELECT COUNT(*) FROM participants WHERE status = 'pending_payment'") as cursor:
                stats["pending_payment"] = (await cursor.fetchone())[0]
            
            # Активных заданий
            async with db.execute("SELECT COUNT(*) FROM tasks WHERE is_active = 1") as cursor:
                stats["active_tasks"] = (await cursor.fetchone())[0]
            
            return stats

