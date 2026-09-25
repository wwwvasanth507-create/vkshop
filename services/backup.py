import os
import json
import sqlalchemy as sa
from datetime import datetime
from database import db

class BackupService:
    @staticmethod
    def get_backup_dir():
        base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        backup_dir = os.path.join(base_dir, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        return backup_dir

    @classmethod
    def backup_database(cls):
        """
        Creates a JSON backup of all tables in the database.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"ecommerce_backup_{timestamp}.json"
        backup_path = os.path.join(cls.get_backup_dir(), backup_filename)
        
        try:
            backup_data = {}
            for model in db.Model.__subclasses__():
                table_name = getattr(model, '__tablename__', None)
                if not table_name:
                    continue
                    
                rows = db.session.query(model).all()
                table_rows = []
                for row in rows:
                    row_dict = {}
                    for col in row.__table__.columns:
                        val = getattr(row, col.name)
                        if isinstance(val, datetime):
                            row_dict[col.name] = val.isoformat()
                        else:
                            row_dict[col.name] = val
                    table_rows.append(row_dict)
                backup_data[table_name] = table_rows
                
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)
                
            return True, backup_filename
        except Exception as e:
            return False, str(e)

    @classmethod
    def list_backups(cls):
        backup_dir = cls.get_backup_dir()
        files = [f for f in os.listdir(backup_dir) if f.endswith('.json')]
        files.sort(reverse=True)
        return files

    @classmethod
    def restore_database(cls, backup_filename):
        """
        Restores the database state from a JSON backup file.
        """
        backup_path = os.path.join(cls.get_backup_dir(), backup_filename)
        if not os.path.exists(backup_path):
            return False, "Backup file not found."
            
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
                
            db.session.remove()
            db.engine.dispose()
            
            dialect_name = db.engine.dialect.name
            
            # Map table names to model classes
            name_to_model = {}
            for model in db.Model.__subclasses__():
                table_name = getattr(model, '__tablename__', None)
                if table_name:
                    name_to_model[table_name] = model

            # Disable foreign key constraints during restore
            if dialect_name == 'sqlite':
                db.session.execute(db.text("PRAGMA foreign_keys = OFF;"))
            else:
                db.session.execute(db.text("SET session_replication_role = 'replica';"))

            try:
                # Clear all existing data in tables present in the backup
                for table_name in backup_data.keys():
                    model = name_to_model.get(table_name)
                    if model:
                        db.session.query(model).delete()
                
                # Insert data from backup
                for table_name, rows in backup_data.items():
                    model = name_to_model.get(table_name)
                    if not model:
                        continue
                        
                    # Find datetime columns for proper parsing
                    datetime_cols = {col.name for col in model.__table__.columns if isinstance(col.type, sa.DateTime)}
                    
                    for row_dict in rows:
                        for col_name in datetime_cols:
                            val = row_dict.get(col_name)
                            if val:
                                try:
                                    row_dict[col_name] = datetime.fromisoformat(val)
                                except Exception:
                                    pass
                        
                        row_obj = model(**row_dict)
                        db.session.add(row_obj)
                        
                db.session.commit()
            finally:
                # Re-enable foreign key constraints
                if dialect_name == 'sqlite':
                    db.session.execute(db.text("PRAGMA foreign_keys = ON;"))
                else:
                    db.session.execute(db.text("SET session_replication_role = 'origin';"))
                    db.session.commit()
                    
            return True, "Database restored successfully."
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @classmethod
    def export_table_json(cls, table_model):
        """
        Exports a database table model's rows to a JSON structure.
        """
        try:
            rows = db.session.query(table_model).all()
            data = []
            for row in rows:
                row_dict = {}
                for col in row.__table__.columns:
                    val = getattr(row, col.name)
                    if isinstance(val, datetime):
                        row_dict[col.name] = val.isoformat()
                    else:
                        row_dict[col.name] = val
                data.append(row_dict)
            return json.dumps(data, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
