import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import Counter, defaultdict
import os
import datetime

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("ADVERTENCIA: Librería 'pandas' no encontrada. La importación desde Excel no funcionará.")
    print("Instálala con: pip install pandas openpyxl")

# --- Configuración ---
HOST_DATA_DIR = "condominio_db_data"
DB_NAME = os.path.join(HOST_DATA_DIR, 'condominio.db')
GRAFICOS_DIR = os.path.join(HOST_DATA_DIR, 'graficos_votaciones')

# Constantes para estados de pregunta
ESTADO_PREGUNTA_INACTIVA = 'inactiva'
ESTADO_PREGUNTA_ACTIVA = 'activa'
ESTADO_PREGUNTA_CERRADA = 'cerrada'

# Constantes para tipos de asistente (en tabla asistencia)
TIPO_ASISTENTE_PROPIETARIO = 'Propietario'
TIPO_ASISTENTE_APODERADO = 'Apoderado'

# Constante para opción por defecto
OPCION_NO_VOTO = "No Votó"


# --- Funciones de Base de Datos e Inicialización ---
def init_app_dirs_and_db():
    """Inicializa directorios y la DB con la nueva estructura v9."""
    if not os.path.exists(HOST_DATA_DIR):
        try:
            os.makedirs(HOST_DATA_DIR)
        except OSError as e:
            print(f"Error creando {HOST_DATA_DIR}: {e}"); raise
    if not os.path.exists(GRAFICOS_DIR):
        try:
            os.makedirs(GRAFICOS_DIR)
        except OSError as e:
            print(f"Error creando {GRAFICOS_DIR}: {e}")

    conn = sqlite3.connect(DB_NAME);
    cursor = conn.cursor()

    # --- Tabla propietarios ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS propietarios (
        cedula TEXT PRIMARY KEY, 
        nombre TEXT NOT NULL, 
        celular TEXT UNIQUE, 
        activo INTEGER DEFAULT 1
    )
    ''')

    # --- Tabla unidades ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS unidades (
        id_unidad INTEGER PRIMARY KEY AUTOINCREMENT, 
        nombre_unidad TEXT UNIQUE NOT NULL, 
        coeficiente REAL DEFAULT 0.0, 
        cedula_propietario TEXT,
        FOREIGN KEY (cedula_propietario) REFERENCES propietarios(cedula) ON DELETE SET NULL ON UPDATE CASCADE
    )
    ''')

    # --- Tabla asambleas ---
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS asambleas (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, descripcion TEXT)''')

    # --- Tabla poderes ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS poderes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        asamblea_id INTEGER NOT NULL, 
        id_unidad_da_poder INTEGER NOT NULL, 
        cedula_apoderado TEXT NOT NULL, 
        nombre_apoderado TEXT, 
        FOREIGN KEY (asamblea_id) REFERENCES asambleas(id) ON DELETE CASCADE, 
        FOREIGN KEY (id_unidad_da_poder) REFERENCES unidades(id_unidad) ON DELETE CASCADE,
        UNIQUE (asamblea_id, id_unidad_da_poder) 
    )
    ''')

    # --- Tabla asistencia ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS asistencia (
        id_asistencia INTEGER PRIMARY KEY AUTOINCREMENT, 
        asamblea_id INTEGER NOT NULL,
        cedula_asistente TEXT NOT NULL, 
        nombre_asistente TEXT, 
        tipo_asistente TEXT NOT NULL, -- 'Propietario' o 'Apoderado'
        presente INTEGER DEFAULT 0, 
        FOREIGN KEY (asamblea_id) REFERENCES asambleas(id) ON DELETE CASCADE,
        UNIQUE (asamblea_id, cedula_asistente)
    )
    ''')

    # --- Tabla preguntas ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS preguntas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        asamblea_id INTEGER NOT NULL, 
        texto_pregunta TEXT NOT NULL,
        opciones_configuradas TEXT, 
        estado TEXT DEFAULT 'inactiva', 
        FOREIGN KEY (asamblea_id) REFERENCES asambleas(id) ON DELETE CASCADE
    )
    ''')

    # --- Tabla votos ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS votos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        pregunta_id INTEGER NOT NULL, 
        id_unidad_representada INTEGER NOT NULL, 
        cedula_ejecuta_voto TEXT, 
        opcion_elegida TEXT NOT NULL, 
        FOREIGN KEY (pregunta_id) REFERENCES preguntas(id) ON DELETE CASCADE, 
        FOREIGN KEY (id_unidad_representada) REFERENCES unidades(id_unidad) ON DELETE CASCADE,
        UNIQUE (pregunta_id, id_unidad_representada) 
    )
    ''')

    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit();
    conn.close()


# --- Clases de la Aplicación ---
class App:
    def __init__(self, root):
        self.root = root;
        self.root.title("Gestión Asambleas Condominio v9");
        self.root.geometry("1250x850")
        style = ttk.Style();
        style.theme_use('clam')
        self.current_assembly_id = None;
        self.current_question_id = None
        self.current_question_options = [];
        self.editing_question_id = None
        self.asistencia_data = {}
        self.excel_file_path = tk.StringVar()

        self.notebook = ttk.Notebook(root)

        self.propietario_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.propietario_tab, text='Propietarios');
        self.setup_propietario_tab()
        self.unidad_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.unidad_tab, text='Unidades');
        self.setup_unidad_tab()
        self.asamblea_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.asamblea_tab, text='Asambleas/Poderes');
        self.setup_asamblea_tab()
        self.asistencia_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.asistencia_tab, text='Asistencia');
        self.setup_asistencia_tab()
        self.voting_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.voting_tab, text='Votación');
        self.setup_voting_tab()
        self.lista_vt_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.lista_vt_tab, text='Lista Votación');
        self.setup_lista_vt_tab()
        self.import_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.import_tab, text='Importar Excel');
        self.setup_import_tab()

        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)
        init_app_dirs_and_db()
        self.load_propietarios();
        self.load_unidades();
        self.load_asambleas()

    def execute_query(self, query, params=(), fetchone=False, fetchall=False, commit=False):
        conn = sqlite3.connect(DB_NAME);
        conn.execute("PRAGMA foreign_keys = ON");
        cursor = conn.cursor();
        result = None
        try:
            cursor.execute(query, params)
            if commit: conn.commit()
            result = cursor.fetchone() if fetchone else cursor.fetchall() if fetchall else None
        except sqlite3.Error as e:
            messagebox.showerror("Error DB", f"Detalle: {e}\nQ: {query}\nP: {params}"); print(
                f"Error DB: {e}\nQ: {query}\nP: {params}");
        finally:
            if conn: conn.close()
        return result

    # --- Pestaña Propietarios ---
    def setup_propietario_tab(self):
        frame = self.propietario_tab;
        form_frame = ttk.LabelFrame(frame, text="Registrar/Actualizar Propietario", padding=10);
        form_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(form_frame, text="Cédula:").grid(row=0, column=0, padx=5, pady=5, sticky="w");
        self.prop_cedula_entry = ttk.Entry(form_frame, width=40);
        self.prop_cedula_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(form_frame, text="Nombre:").grid(row=1, column=0, padx=5, pady=5, sticky="w");
        self.prop_nombre_entry = ttk.Entry(form_frame, width=40);
        self.prop_nombre_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(form_frame, text="Celular:").grid(row=2, column=0, padx=5, pady=5, sticky="w");
        self.prop_celular_entry = ttk.Entry(form_frame, width=40);
        self.prop_celular_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.prop_cedula_to_update = None
        button_frame = ttk.Frame(form_frame);
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text="Guardar", command=self.save_propietario).pack(side=tk.LEFT, padx=5);
        ttk.Button(button_frame, text="Limpiar", command=self.clear_propietario_fields).pack(side=tk.LEFT, padx=5)
        list_frame = ttk.LabelFrame(frame, text="Lista Propietarios", padding=10);
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)
        columns = ("cedula", "nombre", "celular", "estado_act")
        self.propietario_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        for col in columns: self.propietario_tree.heading(col, text=col.replace('_',
                                                                                ' ').capitalize()); self.propietario_tree.column(
            col, width=150 if col != "nombre" else 250, anchor=tk.W)
        self.propietario_tree.pack(fill="both", expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.propietario_tree.yview);
        self.propietario_tree.configure(yscrollcommand=scrollbar.set);
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.propietario_tree.bind("<<TreeviewSelect>>", self.on_propietario_select)
        actions_frame = ttk.Frame(list_frame);
        actions_frame.pack(pady=5, fill="x")
        ttk.Button(actions_frame, text="Activar/Desactivar", command=self.toggle_propietario_activation).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(actions_frame, text="Refrescar", command=self.load_propietarios).pack(side=tk.LEFT, padx=5)

    def clear_propietario_fields(self):
        self.prop_cedula_entry.config(state='normal');
        self.prop_cedula_entry.delete(0, tk.END)
        self.prop_nombre_entry.delete(0, tk.END);
        self.prop_celular_entry.delete(0, tk.END)
        self.prop_cedula_to_update = None;
        self.prop_cedula_entry.focus()

    def save_propietario(self):
        cedula = self.prop_cedula_entry.get().strip();
        nombre = self.prop_nombre_entry.get().strip();
        celular = self.prop_celular_entry.get().strip()
        if not cedula or not nombre: messagebox.showerror("Error", "Cédula y Nombre obligatorios."); return
        try:
            if self.prop_cedula_to_update:
                self.execute_query("UPDATE propietarios SET nombre=?, celular=? WHERE cedula=?",
                                   (nombre, celular, self.prop_cedula_to_update), commit=True);
                messagebox.showinfo("Éxito", "Propietario actualizado.")
            else:
                self.execute_query(
                    "INSERT OR IGNORE INTO propietarios (cedula, nombre, celular, activo) VALUES (?, ?, ?, 1)",
                    (cedula, nombre, celular), commit=True);
                # Verificar si se insertó o se ignoró
                if self.execute_query("SELECT 1 FROM propietarios WHERE cedula = ?", (cedula,), fetchone=True):
                    messagebox.showinfo("Éxito", "Propietario registrado (o ya existía).")
                else:  # No debería pasar con INSERT OR IGNORE si la cédula es PK, pero por si acaso
                    messagebox.showerror("Error", "No se pudo registrar el propietario.")

            self.clear_propietario_fields();
            self.load_propietarios()
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: propietarios.celular" in str(e) and celular:
                messagebox.showerror("Duplicado", f"Celular '{celular}' ya existe.")
            else:
                messagebox.showerror("Error DB", f"Error: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Error inesperado: {e}")

    def on_propietario_select(self, event=None):
        selected = self.propietario_tree.focus();
        if not selected: return
        values = self.propietario_tree.item(selected, "values")
        if values:
            self.prop_cedula_to_update = values[0];
            self.prop_cedula_entry.config(state='normal');
            self.prop_cedula_entry.delete(0, tk.END);
            self.prop_cedula_entry.insert(0, values[0]);
            self.prop_cedula_entry.config(state='disabled')
            self.prop_nombre_entry.delete(0, tk.END);
            self.prop_nombre_entry.insert(0, values[1])
            self.prop_celular_entry.delete(0, tk.END);
            self.prop_celular_entry.insert(0, values[2] if values[2] else "")

    def load_propietarios(self):
        for i in self.propietario_tree.get_children(): self.propietario_tree.delete(i)
        rows = self.execute_query(
            "SELECT cedula, nombre, celular, activo FROM propietarios ORDER BY activo DESC, nombre", fetchall=True)
        if rows:
            for row in rows: estado = "Activo" if row[3] == 1 else "Inactivo"; self.propietario_tree.insert("", "end",
                                                                                                            values=(
                                                                                                            row[0],
                                                                                                            row[1], row[
                                                                                                                2] or "",
                                                                                                            estado))
        self.update_propietario_comboboxes()

    def update_propietario_comboboxes(self):
        props = self.execute_query("SELECT cedula, nombre FROM propietarios WHERE activo = 1 ORDER BY nombre",
                                   fetchall=True)
        prop_list = [f"{p[0]}: {p[1]}" for p in props] if props else []
        if hasattr(self, 'unidad_propietario_combo'): self.unidad_propietario_combo[
            'values'] = prop_list; self.unidad_propietario_combo.set('')

    def toggle_propietario_activation(self):
        selected = self.propietario_tree.focus();
        if not selected: messagebox.showwarning("Advertencia", "Seleccione propietario."); return
        values = self.propietario_tree.item(selected, "values");
        cedula = values[0];
        nombre = values[1];
        estado = values[3]
        nuevo_estado = 0 if estado == "Activo" else 1;
        accion = "desactivar" if nuevo_estado == 0 else "activar"
        if messagebox.askyesno(f"Confirmar", f"¿{accion.capitalize()} a '{nombre}' ({cedula})?"):
            try:
                self.execute_query(f"UPDATE propietarios SET activo = ? WHERE cedula=?", (nuevo_estado, cedula),
                                   commit=True);
                messagebox.showinfo("Éxito", f"Propietario {accion}do.");
                self.load_propietarios();
                self.clear_propietario_fields()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo actualizar: {e}")

    # --- Pestaña Unidades ---
    def setup_unidad_tab(self):
        # (Sin cambios)
        frame = self.unidad_tab;
        form_frame = ttk.LabelFrame(frame, text="Registrar/Actualizar Unidad", padding=10);
        form_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(form_frame, text="Nombre Unidad:").grid(row=0, column=0, padx=5, pady=5, sticky="w");
        self.unidad_nombre_entry = ttk.Entry(form_frame, width=30);
        self.unidad_nombre_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(form_frame, text="Coeficiente:").grid(row=1, column=0, padx=5, pady=5, sticky="w");
        self.unidad_coef_entry = ttk.Entry(form_frame, width=30);
        self.unidad_coef_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(form_frame, text="Propietario:").grid(row=2, column=0, padx=5, pady=5, sticky="w");
        self.unidad_propietario_combo = ttk.Combobox(form_frame, state="readonly", width=28);
        self.unidad_propietario_combo.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.unidad_id_to_update = None
        button_frame = ttk.Frame(form_frame);
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text="Guardar Unidad", command=self.save_unidad).pack(side=tk.LEFT, padx=5);
        ttk.Button(button_frame, text="Limpiar", command=self.clear_unidad_fields).pack(side=tk.LEFT, padx=5)
        list_frame = ttk.LabelFrame(frame, text="Lista Unidades", padding=10);
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)
        columns = ("id_u", "nombre_u", "coef", "ced_prop", "nom_prop")
        self.unidad_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self.unidad_tree.heading("id_u", text="ID");
        self.unidad_tree.column("id_u", width=40, anchor=tk.W)
        self.unidad_tree.heading("nombre_u", text="Unidad");
        self.unidad_tree.column("nombre_u", width=100, anchor=tk.W)
        self.unidad_tree.heading("coef", text="Coef.");
        self.unidad_tree.column("coef", width=80, anchor=tk.E)
        self.unidad_tree.heading("ced_prop", text="Cédula Prop.");
        self.unidad_tree.column("ced_prop", width=120, anchor=tk.W)
        self.unidad_tree.heading("nom_prop", text="Nombre Prop.");
        self.unidad_tree.column("nom_prop", width=200, anchor=tk.W)
        self.unidad_tree.pack(fill="both", expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.unidad_tree.yview);
        self.unidad_tree.configure(yscrollcommand=scrollbar.set);
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.unidad_tree.bind("<<TreeviewSelect>>", self.on_unidad_select)
        actions_frame = ttk.Frame(list_frame);
        actions_frame.pack(pady=5, fill="x")
        ttk.Button(actions_frame, text="Eliminar Unidad", command=self.delete_unidad).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions_frame, text="Refrescar", command=self.load_unidades).pack(side=tk.LEFT, padx=5)

    def clear_unidad_fields(self):
        self.unidad_id_to_update = None;
        self.unidad_nombre_entry.config(state='normal')
        self.unidad_nombre_entry.delete(0, tk.END);
        self.unidad_coef_entry.delete(0, tk.END);
        self.unidad_propietario_combo.set('')
        self.unidad_nombre_entry.focus()

    def save_unidad(self):
        nombre_u = self.unidad_nombre_entry.get().strip();
        coef_str = self.unidad_coef_entry.get().strip();
        prop_sel = self.unidad_propietario_combo.get()
        if not nombre_u or not coef_str or not prop_sel: messagebox.showerror("Error",
                                                                              "Nombre, Coeficiente y Propietario obligatorios."); return
        try:
            coef = float(coef_str.replace(',', '.'))
        except ValueError:
            messagebox.showerror("Error", "Coeficiente numérico."); return
        try:
            ced_prop = prop_sel.split(":")[0].strip()
        except IndexError:
            messagebox.showerror("Error", "Seleccione propietario válido."); return
        try:
            if self.unidad_id_to_update:
                self.execute_query("UPDATE unidades SET coeficiente=?, cedula_propietario=? WHERE id_unidad=?",
                                   (coef, ced_prop, self.unidad_id_to_update), commit=True);
                messagebox.showinfo("Éxito", "Unidad actualizada.")
            else:
                self.execute_query(
                    "INSERT OR IGNORE INTO unidades (nombre_unidad, coeficiente, cedula_propietario) VALUES (?, ?, ?)",
                    (nombre_u, coef, ced_prop), commit=True);
                messagebox.showinfo("Éxito", "Unidad registrada (o ya existía).")
            self.clear_unidad_fields();
            self.load_unidades()
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicado", f"Nombre unidad '{nombre_u}' ya existe.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar: {e}")

    def on_unidad_select(self, event=None):
        selected = self.unidad_tree.focus();
        if not selected: return
        values = self.unidad_tree.item(selected, "values")
        if values:
            self.unidad_id_to_update = values[0];
            self.unidad_nombre_entry.config(state='normal');
            self.unidad_nombre_entry.delete(0, tk.END);
            self.unidad_nombre_entry.insert(0, values[1]);
            self.unidad_nombre_entry.config(state='disabled')
            self.unidad_coef_entry.delete(0, tk.END);
            self.unidad_coef_entry.insert(0, values[2])
            ced_prop = values[3];
            prop_display = f"{ced_prop}: {values[4]}"
            if prop_display in self.unidad_propietario_combo['values']:
                self.unidad_propietario_combo.set(prop_display)
            else:
                self.unidad_propietario_combo.set('')

    def load_unidades(self):
        for i in self.unidad_tree.get_children(): self.unidad_tree.delete(i)
        query = """SELECT u.id_unidad, u.nombre_unidad, u.coeficiente, u.cedula_propietario, p.nombre 
                   FROM unidades u LEFT JOIN propietarios p ON u.cedula_propietario = p.cedula 
                   ORDER BY u.nombre_unidad"""
        rows = self.execute_query(query, fetchall=True)
        if rows:
            for row in rows: self.unidad_tree.insert("", "end", values=row)
        self.update_unidad_comboboxes()

    def update_unidad_comboboxes(self):
        unidades = self.execute_query(
            "SELECT u.id_unidad, u.nombre_unidad, p.nombre FROM unidades u JOIN propietarios p ON u.cedula_propietario = p.cedula WHERE p.activo = 1 ORDER BY u.nombre_unidad",
            fetchall=True)
        unidad_list = [f"{u[0]}: {u[1]} (Prop: {u[2]})" for u in unidades] if unidades else []
        if hasattr(self, 'poder_unidad_combo'): self.poder_unidad_combo[
            'values'] = unidad_list; self.poder_unidad_combo.set('')

    def delete_unidad(self):
        selected = self.unidad_tree.focus();
        if not selected: messagebox.showwarning("Advertencia", "Seleccione unidad."); return
        values = self.unidad_tree.item(selected, "values")
        if messagebox.askyesno("Confirmar",
                               f"¿Eliminar unidad '{values[1]}'? Esto eliminará poderes y votos asociados."):
            try:
                self.execute_query("DELETE FROM unidades WHERE id_unidad=?", (values[0],), commit=True);
                messagebox.showinfo("Éxito", "Unidad eliminada.");
                self.load_unidades();
                self.clear_unidad_fields()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar: {e}")

    # --- Pestaña Asambleas/Poderes ---
    def setup_asamblea_tab(self):
        # (Sin cambios UI)
        frame = self.asamblea_tab;
        assembly_selection_frame = ttk.LabelFrame(frame, text="Gestión Asamblea", padding=10);
        assembly_selection_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(assembly_selection_frame, text="Fecha (YYYY-MM-DD):").grid(row=0, column=0, padx=5, pady=5,
                                                                             sticky="w");
        self.assembly_date_entry = ttk.Entry(assembly_selection_frame, width=30);
        self.assembly_date_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(assembly_selection_frame, text="Descripción:").grid(row=1, column=0, padx=5, pady=5, sticky="w");
        self.assembly_desc_entry = ttk.Entry(assembly_selection_frame, width=30);
        self.assembly_desc_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(assembly_selection_frame, text="Crear Asamblea", command=self.create_assembly).grid(row=2, column=0,
                                                                                                       columnspan=2,
                                                                                                       pady=10)
        assembly_list_frame = ttk.LabelFrame(frame, text="Asambleas Existentes", padding=10);
        assembly_list_frame.pack(padx=10, pady=10, fill="x");
        self.assembly_combobox = ttk.Combobox(assembly_list_frame, state="readonly", width=65);
        self.assembly_combobox.pack(side=tk.LEFT, padx=5);
        self.assembly_combobox.bind("<<ComboboxSelected>>", self.on_assembly_selected)
        powers_frame = ttk.LabelFrame(frame, text="Gestión Poderes", padding=10);
        powers_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(powers_frame, text="Unidad da poder:").grid(row=0, column=0, padx=5, pady=5, sticky="w");
        self.poder_unidad_combo = ttk.Combobox(powers_frame, state="readonly", width=40);
        self.poder_unidad_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(powers_frame, text="Cédula Apoderado:").grid(row=1, column=0, padx=5, pady=5, sticky="w");
        self.poder_cedula_apod_entry = ttk.Entry(powers_frame, width=40);
        self.poder_cedula_apod_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(powers_frame, text="Nombre Apoderado:").grid(row=2, column=0, padx=5, pady=5, sticky="w");
        self.poder_nombre_apod_entry = ttk.Entry(powers_frame, width=40);
        self.poder_nombre_apod_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(powers_frame, text="Asignar Poder", command=self.assign_proxy).grid(row=3, column=0, columnspan=2,
                                                                                       pady=10)
        self.powers_tree = ttk.Treeview(powers_frame, columns=("id_p", "unidad", "propietario", "ced_apod", "nom_apod"),
                                        show="headings", height=4);
        self.powers_tree.heading("id_p", text="ID");
        self.powers_tree.column("id_p", width=30);
        self.powers_tree.heading("unidad", text="Unidad");
        self.powers_tree.column("unidad", width=100);
        self.powers_tree.heading("propietario", text="Propietario");
        self.powers_tree.column("propietario", width=150);
        self.powers_tree.heading("ced_apod", text="Céd. Apod.");
        self.powers_tree.column("ced_apod", width=100);
        self.powers_tree.heading("nom_apod", text="Nom. Apod.");
        self.powers_tree.column("nom_apod", width=150);
        self.powers_tree.grid(row=4, column=0, columnspan=2, pady=5, sticky="ew");
        ttk.Button(powers_frame, text="Eliminar Poder", command=self.delete_proxy).grid(row=5, column=0, columnspan=2,
                                                                                        pady=5)
        questions_frame = ttk.LabelFrame(frame, text="Preguntas Asamblea", padding=10);
        questions_frame.pack(padx=10, pady=10, fill="both", expand=True)
        question_entry_frame = ttk.Frame(questions_frame);
        question_entry_frame.pack(fill="x", pady=5)
        ttk.Label(question_entry_frame, text="Texto Pregunta:").grid(row=0, column=0, padx=5, pady=2, sticky="w");
        self.question_text_entry = ttk.Entry(question_entry_frame, width=50);
        self.question_text_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        ttk.Label(question_entry_frame, text="Opciones (CSV):").grid(row=1, column=0, padx=5, pady=2, sticky="w");
        self.question_options_entry = ttk.Entry(question_entry_frame, width=50);
        self.question_options_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew");
        self.question_options_entry.insert(0, "Acepta,No Acepta,En Blanco")
        question_entry_frame.grid_columnconfigure(1, weight=1)
        question_button_frame = ttk.Frame(questions_frame);
        question_button_frame.pack(fill="x", pady=5)
        ttk.Button(question_button_frame, text="Guardar Pregunta", command=self.save_question).pack(side=tk.LEFT,
                                                                                                    padx=5);
        ttk.Button(question_button_frame, text="Nueva (Limpiar)", command=self.clear_question_fields).pack(side=tk.LEFT,
                                                                                                           padx=5)
        question_list_frame = ttk.Frame(questions_frame);
        question_list_frame.pack(fill="both", expand=True, pady=5)
        self.questions_tree = ttk.Treeview(question_list_frame,
                                           columns=("id_q", "pregunta_t", "opciones_q", "estado_q"), show="headings",
                                           height=5);
        self.questions_tree.heading("id_q", text="ID");
        self.questions_tree.heading("pregunta_t", text="Pregunta");
        self.questions_tree.heading("opciones_q", text="Opciones");
        self.questions_tree.heading("estado_q", text="Estado");
        self.questions_tree.column("id_q", width=30, anchor=tk.W);
        self.questions_tree.column("pregunta_t", width=300, anchor=tk.W);
        self.questions_tree.column("opciones_q", width=200, anchor=tk.W);
        self.questions_tree.column("estado_q", width=100, anchor=tk.W);
        self.questions_tree.pack(side=tk.LEFT, fill="both", expand=True)
        q_scrollbar = ttk.Scrollbar(question_list_frame, orient="vertical", command=self.questions_tree.yview);
        self.questions_tree.configure(yscrollcommand=q_scrollbar.set);
        q_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.questions_tree.bind("<<TreeviewSelect>>", self.on_question_select)

    def save_question(self):
        if not self.current_assembly_id: messagebox.showerror("Error", "Seleccione asamblea."); return
        q_text = self.question_text_entry.get().strip();
        q_options = self.question_options_entry.get().strip()
        if not q_text: messagebox.showerror("Error", "Texto pregunta vacío."); return
        if not q_options: q_options = "Acepta,No Acepta,En Blanco"
        if self.editing_question_id:
            current_state_info = self.execute_query("SELECT estado FROM preguntas WHERE id = ?",
                                                    (self.editing_question_id,), fetchone=True)
            if not current_state_info: messagebox.showerror("Error",
                                                            "Pregunta no existe."); self.clear_question_fields(); self.load_questions_for_assembly(); return
            current_state = current_state_info[0]
            if current_state != ESTADO_PREGUNTA_INACTIVA: messagebox.showerror("Error Edición",
                                                                               f"No se puede editar pregunta '{current_state}'."); return
            try:
                self.execute_query("UPDATE preguntas SET texto_pregunta = ?, opciones_configuradas = ? WHERE id = ?",
                                   (q_text, q_options, self.editing_question_id), commit=True); messagebox.showinfo(
                    "Éxito",
                    "Pregunta actualizada."); self.clear_question_fields(); self.load_questions_for_assembly(); self.load_questions_for_voting_tab()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo actualizar: {e}")
        else:
            try:
                self.execute_query(
                    "INSERT INTO preguntas (asamblea_id, texto_pregunta, opciones_configuradas, estado) VALUES (?, ?, ?, ?)",
                    (self.current_assembly_id, q_text, q_options, ESTADO_PREGUNTA_INACTIVA),
                    commit=True); messagebox.showinfo("Éxito",
                                                      "Pregunta agregada."); self.clear_question_fields(); self.load_questions_for_assembly(); self.load_questions_for_voting_tab()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo agregar: {e}")

    def clear_question_fields(self):
        self.editing_question_id = None;
        self.question_text_entry.config(state='normal');
        self.question_options_entry.config(state='normal')
        self.question_text_entry.delete(0, tk.END);
        self.question_options_entry.delete(0, tk.END);
        self.question_options_entry.insert(0, "Acepta,No Acepta,En Blanco")
        if hasattr(self, 'questions_tree') and self.questions_tree.focus(): self.questions_tree.selection_remove(
            self.questions_tree.focus())

    def on_question_select(self, event=None):
        selected_item = self.questions_tree.focus()
        if not selected_item: self.clear_question_fields(); return
        values = self.questions_tree.item(selected_item, "values")
        if values:
            q_id, q_text, q_options, q_estado_display = values;
            q_estado = q_estado_display.lower()
            self.editing_question_id = int(q_id)
            self.question_text_entry.config(state='normal');
            self.question_options_entry.config(state='normal')
            self.question_text_entry.delete(0, tk.END);
            self.question_text_entry.insert(0, q_text)
            self.question_options_entry.delete(0, tk.END);
            self.question_options_entry.insert(0, q_options)
            if q_estado != ESTADO_PREGUNTA_INACTIVA:
                self.question_text_entry.config(state='disabled'); self.question_options_entry.config(state='disabled')
            else:
                self.question_text_entry.config(state='normal'); self.question_options_entry.config(state='normal')

    def load_questions_for_assembly(self):
        if hasattr(self, 'questions_tree'):
            for i in self.questions_tree.get_children(): self.questions_tree.delete(i)
        if not self.current_assembly_id: return
        questions_data = self.execute_query(
            "SELECT id, texto_pregunta, opciones_configuradas, estado FROM preguntas WHERE asamblea_id = ? ORDER BY id",
            (self.current_assembly_id,), fetchall=True)
        if questions_data:
            for q_id, q_text, q_opts, q_estado in questions_data:
                if hasattr(self, 'questions_tree'): self.questions_tree.insert("", "end", values=(
                q_id, q_text, q_opts, q_estado.capitalize()))

    def create_assembly(self):
        fecha = self.assembly_date_entry.get();
        descripcion = self.assembly_desc_entry.get()
        if not fecha or not descripcion: messagebox.showerror("Error", "Fecha y descripción obligatorias."); return
        try:
            self.execute_query("INSERT INTO asambleas (fecha, descripcion) VALUES (?, ?)", (fecha, descripcion),
                               commit=True); messagebox.showinfo("Éxito",
                                                                 "Asamblea creada."); self.load_asambleas(); self.assembly_date_entry.delete(
                0, tk.END); self.assembly_desc_entry.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear asamblea: {e}")

    def load_asambleas(self):
        assemblies = self.execute_query("SELECT id, fecha, descripcion FROM asambleas ORDER BY fecha DESC, id DESC",
                                        fetchall=True)
        if assemblies is not None:
            assembly_list_display = [f"{row[0]}: {row[1]} - {row[2]}" for row in assemblies]
            self.assembly_combobox['values'] = assembly_list_display
            if hasattr(self, 'asistencia_asamblea_combo'): self.asistencia_asamblea_combo[
                'values'] = assembly_list_display
            if hasattr(self, 'lista_vt_asamblea_combo'): self.lista_vt_asamblea_combo['values'] = assembly_list_display
            if assemblies:
                self.assembly_combobox.current(0);
                if hasattr(self, 'asistencia_asamblea_combo'): self.asistencia_asamblea_combo.current(0)
                if hasattr(self, 'lista_vt_asamblea_combo'): self.lista_vt_asamblea_combo.current(0)
                self.on_assembly_selected();
                self.load_asistencia_for_assembly();
                self.load_questions_for_lista_vt()
            else:
                self.assembly_combobox.set('');
                if hasattr(self, 'asistencia_asamblea_combo'): self.asistencia_asamblea_combo.set('')
                if hasattr(self, 'lista_vt_asamblea_combo'): self.lista_vt_asamblea_combo.set('')
                self.current_assembly_id = None;
                self.clear_assembly_details()
        else:
            self.assembly_combobox['values'] = [];
            self.assembly_combobox.set('');
            if hasattr(self, 'asistencia_asamblea_combo'): self.asistencia_asamblea_combo[
                'values'] = []; self.asistencia_asamblea_combo.set('')
            if hasattr(self, 'lista_vt_asamblea_combo'): self.lista_vt_asamblea_combo[
                'values'] = []; self.lista_vt_asamblea_combo.set('')
            self.current_assembly_id = None;
            self.clear_assembly_details()

    def clear_assembly_details(self):
        if hasattr(self, 'poder_unidad_combo'): self.poder_unidad_combo.set('')
        if hasattr(self, 'poder_cedula_apod_entry'): self.poder_cedula_apod_entry.delete(0, tk.END)
        if hasattr(self, 'poder_nombre_apod_entry'): self.poder_nombre_apod_entry.delete(0, tk.END)
        if hasattr(self, 'powers_tree'):
            for i in self.powers_tree.get_children(): self.powers_tree.delete(i)
        if hasattr(self, 'question_text_entry'): self.question_text_entry.delete(0, tk.END)
        if hasattr(self, 'question_options_entry'):
            self.question_options_entry.delete(0, tk.END);
            self.question_options_entry.insert(0, "Acepta,No Acepta,En Blanco")
        if hasattr(self, 'questions_tree'):
            for i in self.questions_tree.get_children(): self.questions_tree.delete(i)
        self.editing_question_id = None
        self.clear_voting_area()

    def on_assembly_selected(self, event=None):
        selection = self.assembly_combobox.get()
        if selection:
            try:
                new_assembly_id = int(selection.split(":")[0])
                if new_assembly_id != self.current_assembly_id:
                    self.current_assembly_id = new_assembly_id
                    self.load_selected_assembly_details()
                    if hasattr(self, 'asistencia_asamblea_combo'): self.asistencia_asamblea_combo.set(
                        selection); self.load_asistencia_for_assembly()
                    if hasattr(self, 'lista_vt_asamblea_combo'): self.lista_vt_asamblea_combo.set(
                        selection); self.load_questions_for_lista_vt()
            except ValueError:
                messagebox.showerror("Error",
                                     "Selección inválida."); self.current_assembly_id = None; self.clear_assembly_details()
        else:
            self.current_assembly_id = None; self.clear_assembly_details()

    def load_selected_assembly_details(self):
        if not self.current_assembly_id: self.clear_assembly_details(); return
        self.update_propietario_comboboxes();
        self.update_unidad_comboboxes();
        self.load_proxies_for_assembly();
        self.load_questions_for_assembly();
        self.load_questions_for_voting_tab()

    def assign_proxy(self):
        if not self.current_assembly_id: messagebox.showerror("Error", "Seleccione asamblea."); return
        unidad_selection = self.poder_unidad_combo.get();
        cedula_apoderado = self.poder_cedula_apod_entry.get().strip();
        nombre_apoderado = self.poder_nombre_apod_entry.get().strip()
        if not unidad_selection or not cedula_apoderado or not nombre_apoderado: messagebox.showerror("Error",
                                                                                                      "Seleccione Unidad y complete datos Apoderado."); return
        try:
            id_unidad = int(unidad_selection.split(":")[0].strip())
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Selección unidad inválida."); return
        propietario_unidad = self.execute_query("SELECT cedula_propietario FROM unidades WHERE id_unidad = ?",
                                                (id_unidad,), fetchone=True)
        if propietario_unidad and propietario_unidad[0] == cedula_apoderado: messagebox.showerror("Error",
                                                                                                  "Propietario no puede ser apoderado de su unidad."); return
        try:
            self.execute_query(
                "INSERT INTO poderes (asamblea_id, id_unidad_da_poder, cedula_apoderado, nombre_apoderado) VALUES (?, ?, ?, ?)",
                (self.current_assembly_id, id_unidad, cedula_apoderado, nombre_apoderado), commit=True)
            messagebox.showinfo("Éxito", "Poder asignado.");
            self.load_proxies_for_assembly();
            self.poder_cedula_apod_entry.delete(0, tk.END);
            self.poder_nombre_apod_entry.delete(0, tk.END);
            self.poder_unidad_combo.set('')
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Ya existe poder para esta unidad en esta asamblea.");
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo asignar: {e}")

    def load_proxies_for_assembly(self):
        for i in self.powers_tree.get_children(): self.powers_tree.delete(i)
        if not self.current_assembly_id: return
        query = """SELECT p.id, u.nombre_unidad, pr.nombre, p.cedula_apoderado, p.nombre_apoderado FROM poderes p JOIN unidades u ON p.id_unidad_da_poder = u.id_unidad JOIN propietarios pr ON u.cedula_propietario = pr.cedula WHERE p.asamblea_id = ? ORDER BY u.nombre_unidad"""
        proxies = self.execute_query(query, (self.current_assembly_id,), fetchall=True)
        if proxies:
            for id_p, nom_u, nom_prop, ced_apod, nom_apod in proxies: self.powers_tree.insert("", "end", values=(
            id_p, nom_u, nom_prop, ced_apod, nom_apod))

    def delete_proxy(self):
        selected = self.powers_tree.focus();
        if not selected: messagebox.showwarning("Advertencia", "Seleccione poder."); return
        if not self.current_assembly_id: messagebox.showerror("Error", "No hay asamblea."); return
        if messagebox.askyesno("Confirmar", "¿Eliminar poder?"):
            power_id = self.powers_tree.item(selected, "values")[0]
            try:
                self.execute_query("DELETE FROM poderes WHERE id=? AND asamblea_id=?",
                                   (power_id, self.current_assembly_id), commit=True); messagebox.showinfo("Éxito",
                                                                                                           "Poder eliminado."); self.load_proxies_for_assembly();
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar: {e}")

    # --- Pestaña Asistencia ---
    def setup_asistencia_tab(self):
        frame = self.asistencia_tab;
        asamblea_select_frame = ttk.LabelFrame(frame, text="Seleccionar Asamblea", padding=10);
        asamblea_select_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(asamblea_select_frame, text="Asamblea:").pack(side=tk.LEFT, padx=5);
        self.asistencia_asamblea_combo = ttk.Combobox(asamblea_select_frame, state="readonly", width=60);
        self.asistencia_asamblea_combo.pack(side=tk.LEFT, padx=5);
        self.asistencia_asamblea_combo.bind("<<ComboboxSelected>>", self.on_asistencia_assembly_selected);
        ttk.Button(asamblea_select_frame, text="Cargar", command=self.load_asistencia_for_assembly).pack(side=tk.LEFT,
                                                                                                         padx=5)
        list_frame = ttk.LabelFrame(frame, text="Registro Asistencia", padding=10);
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)
        columns = ("cedula", "nombre", "tipo", "presente");
        self.asistencia_tree = ttk.Treeview(list_frame, columns=columns, show="headings");
        self.asistencia_tree.heading("cedula", text="Cédula");
        self.asistencia_tree.column("cedula", width=120);
        self.asistencia_tree.heading("nombre", text="Nombre");
        self.asistencia_tree.column("nombre", width=250);
        self.asistencia_tree.heading("tipo", text="Tipo");
        self.asistencia_tree.column("tipo", width=100);
        self.asistencia_tree.heading("presente", text="Presente");
        self.asistencia_tree.column("presente", width=80, anchor=tk.CENTER);
        self.asistencia_tree.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.asistencia_tree.yview);
        self.asistencia_tree.configure(yscrollcommand=scrollbar.set);
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.asistencia_tree.bind("<Button-1>", self.toggle_asistencia_on_click)
        add_apod_frame = ttk.LabelFrame(frame, text="Añadir Apoderado a Lista", padding=10);
        add_apod_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(add_apod_frame, text="Cédula Apod.:").grid(row=0, column=0, padx=5, pady=2, sticky="w");
        self.asistencia_apod_cedula_entry = ttk.Entry(add_apod_frame, width=20);
        self.asistencia_apod_cedula_entry.grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(add_apod_frame, text="Nombre Apod.:").grid(row=0, column=2, padx=5, pady=2, sticky="w");
        self.asistencia_apod_nombre_entry = ttk.Entry(add_apod_frame, width=30);
        self.asistencia_apod_nombre_entry.grid(row=0, column=3, padx=5, pady=2, sticky="ew")
        ttk.Button(add_apod_frame, text="Añadir", command=self.add_apoderado_to_asistencia).grid(row=0, column=4,
                                                                                                 padx=10, pady=2);
        add_apod_frame.grid_columnconfigure(3, weight=1)
        save_button_frame = ttk.Frame(frame);
        save_button_frame.pack(pady=10);
        ttk.Button(save_button_frame, text="Guardar Cambios Asistencia", command=self.save_asistencia_changes).pack()

    def on_asistencia_assembly_selected(self, event=None):
        selection = self.asistencia_asamblea_combo.get()
        if selection:
            try:
                asamblea_id = int(selection.split(":")[0])
                if asamblea_id != self.current_assembly_id:
                    self.assembly_combobox.set(selection)
                    self.on_assembly_selected()
                else:
                    self.load_asistencia_for_assembly()
            except (ValueError, IndexError):
                messagebox.showerror("Error", "Selección inválida.")

    def load_asistencia_for_assembly(self, event=None):
        self.clear_asistencia_list();
        selection = self.asistencia_asamblea_combo.get();
        if not selection: return
        try:
            asamblea_id = int(selection.split(":")[0])
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Selección inválida."); return
        propietarios = self.execute_query("SELECT cedula, nombre FROM propietarios WHERE activo = 1 ORDER BY nombre",
                                          fetchall=True)
        apoderados_poder = self.execute_query(
            "SELECT DISTINCT cedula_apoderado, nombre_apoderado FROM poderes WHERE asamblea_id = ?", (asamblea_id,),
            fetchall=True)
        asistencia_existente = self.execute_query(
            "SELECT cedula_asistente, presente FROM asistencia WHERE asamblea_id = ?", (asamblea_id,), fetchall=True)
        asistencia_map = {row[0]: row[1] for row in asistencia_existente} if asistencia_existente else {};
        self.asistencia_data = {}
        if propietarios:
            for cedula, nombre in propietarios: presente_db = asistencia_map.get(cedula,
                                                                                 0); presente_str = "Sí" if presente_db == 1 else "No"; item_id = self.asistencia_tree.insert(
                "", "end", values=(cedula, nombre, TIPO_ASISTENTE_PROPIETARIO, presente_str)); self.asistencia_data[
                item_id] = {'cedula': cedula, 'presente': presente_db, 'tipo': TIPO_ASISTENTE_PROPIETARIO,
                            'nombre': nombre}
        apoderados_added = set()
        if apoderados_poder:
            for cedula_apod, nombre_apod in apoderados_poder:
                if cedula_apod not in apoderados_added: presente_db = asistencia_map.get(cedula_apod,
                                                                                         0); presente_str = "Sí" if presente_db == 1 else "No"; item_id = self.asistencia_tree.insert(
                    "", "end", values=(cedula_apod, nombre_apod, TIPO_ASISTENTE_APODERADO, presente_str));
                self.asistencia_data[item_id] = {'cedula': cedula_apod, 'presente': presente_db,
                                                 'tipo': TIPO_ASISTENTE_APODERADO,
                                                 'nombre': nombre_apod}; apoderados_added.add(cedula_apod)
        if asistencia_existente:
            for cedula_asist, presente_db in asistencia_map.items():
                is_propietario = any(p[0] == cedula_asist for p in propietarios or [])
                if not is_propietario and cedula_asist not in apoderados_added:
                    asist_info = self.execute_query(
                        "SELECT nombre_asistente FROM asistencia WHERE asamblea_id = ? AND cedula_asistente = ?",
                        (asamblea_id, cedula_asist), fetchone=True)
                    nombre_asist = asist_info[0] if asist_info else "Desconocido";
                    presente_str = "Sí" if presente_db == 1 else "No";
                    item_id = self.asistencia_tree.insert("", "end", values=(
                    cedula_asist, nombre_asist, TIPO_ASISTENTE_APODERADO, presente_str));
                    self.asistencia_data[item_id] = {'cedula': cedula_asist, 'presente': presente_db,
                                                     'tipo': TIPO_ASISTENTE_APODERADO, 'nombre': nombre_asist};
                    apoderados_added.add(cedula_asist)

    def toggle_asistencia_on_click(self, event):
        region = self.asistencia_tree.identify_region(event.x, event.y)
        if region != "cell": return
        item_id = self.asistencia_tree.focus()
        if not item_id: return
        if item_id in self.asistencia_data:
            current_state = self.asistencia_data[item_id]['presente'];
            new_state = 1 - current_state
            self.asistencia_data[item_id]['presente'] = new_state
            presente_str = "Sí" if new_state == 1 else "No"
            current_values = list(self.asistencia_tree.item(item_id, 'values'));
            current_values[3] = presente_str
            self.asistencia_tree.item(item_id, values=tuple(current_values))

    def add_apoderado_to_asistencia(self):
        cedula_apod = self.asistencia_apod_cedula_entry.get().strip();
        nombre_apod = self.asistencia_apod_nombre_entry.get().strip()
        if not cedula_apod or not nombre_apod: messagebox.showerror("Error", "Ingrese Cédula y Nombre."); return
        if any(data['cedula'] == cedula_apod for data in self.asistencia_data.values()): messagebox.showwarning(
            "Advertencia", "Cédula ya en lista."); return
        presente_str = "Sí";
        presente_int = 1
        item_id = self.asistencia_tree.insert("", "end",
                                              values=(cedula_apod, nombre_apod, TIPO_ASISTENTE_APODERADO, presente_str))
        self.asistencia_data[item_id] = {'cedula': cedula_apod, 'presente': presente_int,
                                         'tipo': TIPO_ASISTENTE_APODERADO, 'nombre': nombre_apod}
        self.asistencia_apod_cedula_entry.delete(0, tk.END);
        self.asistencia_apod_nombre_entry.delete(0, tk.END)

    def save_asistencia_changes(self):
        selection = self.asistencia_asamblea_combo.get()
        if not selection: messagebox.showerror("Error", "Seleccione asamblea."); return
        try:
            asamblea_id = int(selection.split(":")[0])
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Selección inválida."); return
        if not self.asistencia_data: messagebox.showinfo("Info", "No hay datos para guardar."); return
        data_to_save = [(asamblea_id, data['cedula'], data['nombre'], data['tipo'], data['presente']) for data in
                        self.asistencia_data.values()]
        conn = sqlite3.connect(DB_NAME);
        conn.execute("PRAGMA foreign_keys = ON");
        cursor = conn.cursor()
        try:
            cursor.executemany(
                "INSERT OR REPLACE INTO asistencia (asamblea_id, cedula_asistente, nombre_asistente, tipo_asistente, presente) VALUES (?, ?, ?, ?, ?)",
                data_to_save)
            conn.commit();
            messagebox.showinfo("Éxito", f"Asistencia para asamblea {asamblea_id} guardada.")
        except sqlite3.Error as e:
            conn.rollback(); messagebox.showerror("Error DB", f"No se pudo guardar: {e}")
        finally:
            conn.close()
        self.load_asistencia_for_assembly()

    # --- Pestaña Votación ---
    def setup_voting_tab(self):
        frame = self.voting_tab;
        question_select_frame = ttk.LabelFrame(frame, text="Seleccionar Pregunta", padding=10);
        question_select_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(question_select_frame, text="Pregunta:").pack(side=tk.LEFT, padx=5);
        self.voting_question_combobox = ttk.Combobox(question_select_frame, state="readonly", width=70);
        self.voting_question_combobox.pack(side=tk.LEFT, padx=5);
        self.voting_question_combobox.bind("<<ComboboxSelected>>", self.on_voting_question_selected_for_display)
        button_frame_votacion = ttk.Frame(question_select_frame);
        button_frame_votacion.pack(side=tk.LEFT, padx=10);
        ttk.Button(button_frame_votacion, text="Activar", command=self.activate_question_for_voting).pack(side=tk.TOP,
                                                                                                          pady=2);
        ttk.Button(button_frame_votacion, text="Cerrar", command=self.close_current_question_voting).pack(side=tk.TOP,
                                                                                                          pady=2)
        self.active_question_label = ttk.Label(frame, text="Pregunta Activa: Ninguna", font=("Arial", 12, "bold"));
        self.active_question_label.pack(pady=10)
        vote_entry_frame = ttk.LabelFrame(frame, text="Registrar Voto Manual", padding=10);
        vote_entry_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(vote_entry_frame, text="Votante Elegible:").grid(row=0, column=0, padx=5, pady=5, sticky="w");
        self.voting_resident_combobox = ttk.Combobox(vote_entry_frame, state="readonly", width=40);
        self.voting_resident_combobox.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(vote_entry_frame, text="Opción Voto:").grid(row=1, column=0, padx=5, pady=5, sticky="nw");
        self.options_radio_frame = ttk.Frame(vote_entry_frame);
        self.options_radio_frame.grid(row=1, column=1, padx=5, pady=5, sticky="ew");
        self.vote_option_var_string = tk.StringVar()
        ttk.Button(vote_entry_frame, text="Registrar Voto", command=self.register_vote).grid(row=2, column=0,
                                                                                             columnspan=2, pady=10);
        vote_entry_frame.grid_columnconfigure(1, weight=1)
        results_frame = ttk.LabelFrame(frame, text="Resultados Pregunta", padding=10);
        results_frame.pack(padx=10, pady=10, fill="both", expand=True);
        self.results_display_frame = results_frame;
        self.results_canvas_widget = None

    def load_questions_for_voting_tab(self):
        if not self.current_assembly_id: self.voting_question_combobox[
            'values'] = []; self.voting_question_combobox.set(''); self.clear_voting_area(); return
        questions = self.execute_query("SELECT id, texto_pregunta FROM preguntas WHERE asamblea_id = ? ORDER BY id",
                                       (self.current_assembly_id,), fetchall=True)
        if questions is not None:
            self.voting_question_combobox['values'] = [f"{q[0]}: {q[1]}" for q in questions]
            if questions:
                self.voting_question_combobox.current(0); self.on_voting_question_selected_for_display()
            else:
                self.voting_question_combobox.set(''); self.clear_voting_area();
        else:
            self.voting_question_combobox['values'] = []; self.voting_question_combobox.set(
                ''); self.clear_voting_area()

    def clear_voting_area(self):
        self.current_question_id = None;
        self.current_question_options = []
        if hasattr(self, 'active_question_label'): self.active_question_label.config(text="Pregunta Activa: Ninguna")
        if hasattr(self, 'voting_resident_combobox'): self.voting_resident_combobox.set('');
        self.voting_resident_combobox['values'] = []
        if hasattr(self, 'vote_option_var_string'): self.vote_option_var_string.set("")
        if hasattr(self, 'options_radio_frame') and self.options_radio_frame.winfo_exists():
            for widget in self.options_radio_frame.winfo_children(): widget.destroy()
        if hasattr(self,
                   'results_canvas_widget') and self.results_canvas_widget: self.results_canvas_widget.destroy(); self.results_canvas_widget = None
        if hasattr(self, 'results_display_frame') and self.results_display_frame.winfo_exists():
            for widget in self.results_display_frame.winfo_children():
                if widget != self.results_canvas_widget: widget.destroy()

    def on_voting_question_selected_for_display(self, event=None):
        selection = self.voting_question_combobox.get()
        if selection:
            try:
                question_id_to_display = int(selection.split(":")[0])
                if question_id_to_display != self.current_question_id:
                    self.update_vote_options_ui(question_id_to_display, for_display_only=True)
                else:
                    self.update_vote_options_ui(question_id_to_display, for_display_only=False)
                self.display_vote_results_for_question(question_id_to_display)
            except ValueError:
                messagebox.showerror("Error", "Selección inválida.")

    def update_vote_options_ui(self, question_id, for_display_only=False):
        if hasattr(self, 'options_radio_frame') and self.options_radio_frame.winfo_exists():
            for widget in self.options_radio_frame.winfo_children(): widget.destroy()
        self.current_question_options = []
        question_data = self.execute_query("SELECT opciones_configuradas FROM preguntas WHERE id = ?", (question_id,),
                                           fetchone=True)
        if question_data and question_data[0]:
            self.current_question_options = [opt.strip() for opt in question_data[0].split(',')]
        else:
            self.current_question_options = ["Acepta", "No Acepta", "En Blanco"]
        if hasattr(self, 'vote_option_var_string'): self.vote_option_var_string.set("")
        if not for_display_only or self.current_question_id == question_id:
            for option_text in self.current_question_options:
                rb = ttk.Radiobutton(self.options_radio_frame, text=option_text, variable=self.vote_option_var_string,
                                     value=option_text)
                rb.pack(anchor=tk.W, pady=2)
        elif not self.current_question_id and for_display_only:
            if hasattr(self, 'options_radio_frame') and self.options_radio_frame.winfo_exists():
                ttk.Label(self.options_radio_frame, text="Opciones se mostrarán al activar.").pack(anchor=tk.W)

    def activate_question_for_voting(self):
        """Activa pregunta, insertando 'No Votó' para elegibles presentes."""
        selection = self.voting_question_combobox.get();
        if not selection: messagebox.showerror("Error", "Seleccione pregunta."); return
        if not self.current_assembly_id: messagebox.showerror("Error", "Seleccione asamblea."); return
        try:
            new_active_question_id = int(selection.split(":")[0])
        except ValueError:
            messagebox.showerror("Error", "Selección inválida."); return

        q_info = self.execute_query("SELECT estado FROM preguntas WHERE id = ?", (new_active_question_id,),
                                    fetchone=True)
        if not q_info: messagebox.showerror("Error", "Pregunta no encontrada."); return
        if q_info[0] == ESTADO_PREGUNTA_CERRADA: messagebox.showwarning("Advertencia",
                                                                        "Pregunta ya está cerrada."); return
        if q_info[0] == ESTADO_PREGUNTA_ACTIVA: messagebox.showinfo("Info", "Pregunta ya está activa."); return

        # 1. Obtener unidades/votantes elegibles y presentes
        eligible_info = self._get_eligible_voters_info()  # Lista de dicts con id_unidad
        if not eligible_info:
            messagebox.showwarning("Sin Votantes", "No hay votantes elegibles presentes para esta asamblea.")

        # 2. Insertar 'No Votó' inicial para cada unidad elegible
        initial_votes_to_insert = []
        for voter_unit in eligible_info:
            initial_votes_to_insert.append((
                new_active_question_id,
                voter_unit['id_unidad']
            ))

        conn = sqlite3.connect(DB_NAME);
        conn.execute("PRAGMA foreign_keys = ON");
        cursor = conn.cursor()
        inserted_count = 0
        try:
            cursor.executemany(
                f"INSERT OR IGNORE INTO votos (pregunta_id, id_unidad_representada, cedula_ejecuta_voto, opcion_elegida) VALUES (?, ?, NULL, '{OPCION_NO_VOTO}')",
                initial_votes_to_insert)
            inserted_count = cursor.rowcount
            conn.commit()
            print(
                f"INFO: Insertados/Ignorados {inserted_count} votos iniciales como '{OPCION_NO_VOTO}' para pregunta {new_active_question_id}.")
        except sqlite3.Error as e:
            conn.rollback()
            messagebox.showerror("Error DB", f"No se pudo inicializar 'No Votó': {e}")
            return
        finally:
            conn.close()

        # 3. Marcar pregunta como activa y actualizar UI
        if self.current_question_id is not None and self.current_question_id != new_active_question_id:
            self.execute_query("UPDATE preguntas SET estado = ? WHERE id = ? AND asamblea_id = ?",
                               (ESTADO_PREGUNTA_CERRADA, self.current_question_id, self.current_assembly_id),
                               commit=True)
        self.execute_query("UPDATE preguntas SET estado = ? WHERE id = ? AND asamblea_id = ?",
                           (ESTADO_PREGUNTA_ACTIVA, new_active_question_id, self.current_assembly_id), commit=True)

        self.current_question_id = new_active_question_id;
        question_text = selection.split(":", 1)[1].strip()
        self.active_question_label.config(text=f"Pregunta Activa (ID: {self.current_question_id}): {question_text}")

        self.update_vote_options_ui(self.current_question_id, for_display_only=False);
        self.load_eligible_voters_for_voting();
        self.display_vote_results_for_question(self.current_question_id);
        self.load_questions_for_assembly()
        self.load_questions_for_lista_vt()
        messagebox.showinfo("Votación Activada",
                            f"Pregunta '{question_text}' activa. Estado inicial: '{OPCION_NO_VOTO}'.")

    def close_current_question_voting(self):
        """Cierra la votación. Los que no votaron quedan como 'No Votó'."""
        if not self.current_question_id: messagebox.showwarning("Advertencia", "Ninguna pregunta activa."); return
        question_id_to_close = self.current_question_id
        q_info = self.execute_query("SELECT texto_pregunta FROM preguntas WHERE id = ?", (question_id_to_close,),
                                    fetchone=True);
        question_text_closed = q_info[0] if q_info else f"ID {question_id_to_close}"

        # Marcar pregunta como cerrada
        self.execute_query("UPDATE preguntas SET estado = ? WHERE id = ?",
                           (ESTADO_PREGUNTA_CERRADA, question_id_to_close,), commit=True);
        self.load_questions_for_assembly()

        messagebox.showinfo("Votación Cerrada", f"Se cerró votación para: '{question_text_closed}'.");
        self.display_vote_results_for_question(question_id_to_close, final=True)
        self.load_lista_votacion_data()

        self.current_question_id = None;
        self.current_question_options = []
        self.active_question_label.config(text="Pregunta Activa: Ninguna");
        self.voting_resident_combobox.set('');
        self.voting_resident_combobox['values'] = [];
        self.vote_option_var_string.set("")
        if hasattr(self, 'options_radio_frame') and self.options_radio_frame.winfo_exists():
            for widget in self.options_radio_frame.winfo_children(): widget.destroy()

    def _get_eligible_voters_info(self):
        if not self.current_assembly_id: return []
        asistencia = self.execute_query(
            "SELECT cedula_asistente, tipo_asistente FROM asistencia WHERE asamblea_id = ? AND presente = 1",
            (self.current_assembly_id,), fetchall=True)
        if not asistencia: return []
        presentes_map = {row[0]: row[1] for row in asistencia}
        poderes_dados = self.execute_query(
            "SELECT id_unidad_da_poder, cedula_apoderado FROM poderes WHERE asamblea_id = ?",
            (self.current_assembly_id,), fetchall=True)
        unidades_con_poder = {row[0]: row[1] for row in poderes_dados} if poderes_dados else {}
        apoderados_con_poder = {row[1] for row in poderes_dados} if poderes_dados else set()
        unidades = self.execute_query("SELECT id_unidad, nombre_unidad, coeficiente, cedula_propietario FROM unidades",
                                      fetchall=True)
        if not unidades: return []
        eligible_voters = []
        for id_u, nom_u, coef, ced_prop in unidades:
            if not ced_prop: continue
            if ced_prop in presentes_map and presentes_map[
                ced_prop] == TIPO_ASISTENTE_PROPIETARIO and id_u not in unidades_con_poder:
                prop_info = self.execute_query("SELECT nombre FROM propietarios WHERE cedula = ?", (ced_prop,),
                                               fetchone=True)
                eligible_voters.append(
                    {'cedula_ejecuta': ced_prop, 'nombre_ejecuta': prop_info[0] if prop_info else '??',
                     'id_unidad': id_u, 'nombre_unidad': nom_u, 'coeficiente': coef})
            elif id_u in unidades_con_poder:
                ced_apod = unidades_con_poder[id_u]
                if ced_apod in presentes_map:
                    apod_info = self.execute_query(
                        "SELECT nombre_asistente FROM asistencia WHERE asamblea_id = ? AND cedula_asistente = ?",
                        (self.current_assembly_id, ced_apod), fetchone=True)
                    if not apod_info: apod_info = self.execute_query(
                        "SELECT nombre_apoderado FROM poderes WHERE asamblea_id = ? AND cedula_apoderado = ? LIMIT 1",
                        (self.current_assembly_id, ced_apod), fetchone=True)
                    eligible_voters.append(
                        {'cedula_ejecuta': ced_apod, 'nombre_ejecuta': apod_info[0] if apod_info else '??',
                         'id_unidad': id_u, 'nombre_unidad': nom_u, 'coeficiente': coef})
        return eligible_voters

    def load_eligible_voters_for_voting(self):
        self.voting_resident_combobox['values'] = [];
        self.voting_resident_combobox.set('')
        if not self.current_assembly_id: return
        eligible_info = self._get_eligible_voters_info()
        if not eligible_info: return
        combo_list = [
            f"{v['cedula_ejecuta']}: {v['nombre_ejecuta']} (Por: {v['nombre_unidad']} / Coef: {v['coeficiente']})" for v
            in eligible_info]
        self.voting_resident_combobox['values'] = sorted(combo_list)
        if combo_list:
            self.voting_resident_combobox.current(0)
        else:
            self.voting_resident_combobox.set('')

    def register_vote(self):
        if not self.current_question_id: messagebox.showerror("Error", "Ninguna pregunta activa."); return
        voter_selection_text = self.voting_resident_combobox.get();
        opcion_elegida_str = self.vote_option_var_string.get()
        if not voter_selection_text: messagebox.showerror("Error", "Seleccione votante."); return
        if not opcion_elegida_str: messagebox.showerror("Error", "Seleccione opción."); return
        try:
            cedula_ejecuta = voter_selection_text.split(":")[0].strip()
            unidad_info_str = voter_selection_text.split('(Por: ')[1].split(' / Coef:')[0]
            unidad_data = self.execute_query("SELECT id_unidad FROM unidades WHERE nombre_unidad = ?",
                                             (unidad_info_str,), fetchone=True)
            if not unidad_data: raise ValueError(f"No se encontró ID unidad '{unidad_info_str}'")
            id_unidad_representada = unidad_data[0]
        except (IndexError, ValueError) as e:
            messagebox.showerror("Error", f"Error procesando votante: {e}\nTexto: {voter_selection_text}"); return
        try:
            self.execute_query(
                "INSERT OR REPLACE INTO votos (pregunta_id, id_unidad_representada, cedula_ejecuta_voto, opcion_elegida) VALUES (?, ?, ?, ?)",
                (self.current_question_id, id_unidad_representada, cedula_ejecuta, opcion_elegida_str), commit=True)
            messagebox.showinfo("Éxito", "Voto registrado/actualizado.")
            self.display_vote_results_for_question(self.current_question_id);
            self.vote_option_var_string.set("")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar: {e}")

    def get_voting_weights(self):
        unidades = self.execute_query("SELECT id_unidad, coeficiente FROM unidades", fetchall=True)
        return {u[0]: u[1] for u in unidades} if unidades else {}

    def display_vote_results_for_question(self, question_id_for_results, final=False):
        if not self.current_assembly_id: messagebox.showwarning("Advertencia",
                                                                "No hay asamblea."); self.clear_voting_area(); return
        if not question_id_for_results: self.clear_voting_area(); return
        if hasattr(self,
                   'results_canvas_widget') and self.results_canvas_widget: self.results_canvas_widget.destroy(); self.results_canvas_widget = None
        if hasattr(self, 'results_display_frame') and self.results_display_frame.winfo_exists():
            for widget in self.results_display_frame.winfo_children(): widget.destroy()
        q_info = self.execute_query("SELECT texto_pregunta, estado, opciones_configuradas FROM preguntas WHERE id = ?",
                                    (question_id_for_results,), fetchone=True)
        if not q_info:
            if hasattr(self.results_display_frame,
                       'winfo_exists') and self.results_display_frame.winfo_exists(): ttk.Label(
                self.results_display_frame, text=f"Pregunta ID {question_id_for_results} no encontrada.").pack(pady=20)
            return
        q_text, q_estado, q_options_str = q_info;
        q_options_list = [opt.strip() for opt in q_options_str.split(',')] if q_options_str else ["Acepta", "No Acepta",
                                                                                                  "En Blanco"]
        votes_data = self.execute_query(
            "SELECT id_unidad_representada, opcion_elegida FROM votos WHERE pregunta_id = ?",
            (question_id_for_results,), fetchall=True)
        votes_by_unit = {v[0]: v[1] for v in votes_data} if votes_data else {}
        all_unit_weights = self.get_voting_weights();
        total_coeficiente_condominio = sum(all_unit_weights.values())
        weighted_results = Counter();
        voted_units_count = Counter();
        total_coef_voted = 0
        for id_unidad, coef in all_unit_weights.items():
            if id_unidad in votes_by_unit and votes_by_unit[id_unidad] != OPCION_NO_VOTO:
                opcion = votes_by_unit[id_unidad];
                weighted_results[opcion] += coef;
                voted_units_count[opcion] += 1;
                total_coef_voted += coef
        coef_no_voto = total_coeficiente_condominio - total_coef_voted
        if abs(coef_no_voto) < 0.0001: coef_no_voto = 0
        no_voto_label = OPCION_NO_VOTO
        if no_voto_label not in q_options_list: q_options_list.append(no_voto_label)
        weighted_results[no_voto_label] = coef_no_voto
        voted_units_count[no_voto_label] = len(all_unit_weights) - sum(
            v for k, v in voted_units_count.items() if k != no_voto_label)
        chart_labels = [];
        chart_sizes = [];
        options_for_chart = q_options_list
        for option_text_label in options_for_chart:
            coef_for_option = weighted_results[option_text_label]
            percentage = (
                                     coef_for_option / total_coeficiente_condominio) * 100 if total_coeficiente_condominio > 0 else 0
            if coef_for_option > 0.0001: chart_labels.append(
                f"{option_text_label}\n({coef_for_option:.4f} coef, {percentage:.1f}%)"); chart_sizes.append(
                coef_for_option)
            if option_text_label not in voted_units_count: voted_units_count[option_text_label] = 0
        if not chart_sizes:
            if hasattr(self.results_display_frame,
                       'winfo_exists') and self.results_display_frame.winfo_exists(): ttk.Label(
                self.results_display_frame, text=f"Sin votos válidos para graficar:\n'{q_text}'").pack(pady=20)
            return
        fig, ax = plt.subplots(figsize=(6, 4.5));
        wedges, _, autotexts = ax.pie(chart_sizes, labels=None,
                                      autopct=lambda p: '{:.1f}%'.format(p) if p > 0.1 else '', startangle=90,
                                      pctdistance=0.85, wedgeprops=dict(width=0.4));
        ax.axis('equal');
        ax.legend(wedges, chart_labels, title="Opciones", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1),
                  fontsize='small');
        plt.subplots_adjust(left=0.05, right=0.65, top=0.9, bottom=0.05)
        title_text = f"Resultados: {q_text}"
        if final:
            title_text = f"Resultados Finales: {q_text}"
        elif q_estado == ESTADO_PREGUNTA_ACTIVA:
            title_text = f"Resultados Parciales: {q_text} (Votación Abierta)"
        elif q_estado == ESTADO_PREGUNTA_CERRADA:
            title_text = f"Resultados (Votación Cerrada): {q_text}"
        plt.title(title_text, pad=20, loc='center', fontsize=10)
        info_text_lines = [f"Pregunta ID: {question_id_for_results}"];
        info_text_lines.append("\nConteo (unidades):");
        for opt_text in q_options_list: info_text_lines.append(f"- {opt_text}: {voted_units_count[opt_text]}")
        info_text_lines.append(f"\nTotal Coeficiente Condominio: {total_coeficiente_condominio:.4f}");
        info_text_lines.append(f"Coeficiente Votado (excl. No Votó): {total_coef_voted:.4f}")
        if total_coeficiente_condominio > 0: participation = (
                                                                         total_coef_voted / total_coeficiente_condominio) * 100; info_text_lines.append(
            f"Participación (coeficiente): {participation:.1f}%")
        if hasattr(self.results_display_frame, 'winfo_exists') and self.results_display_frame.winfo_exists():
            ttk.Label(self.results_display_frame, text="\n".join(info_text_lines), justify=tk.LEFT,
                      wraplength=380).pack(pady=5, anchor='w', padx=5)
            try:
                if not os.path.exists(GRAFICOS_DIR): os.makedirs(GRAFICOS_DIR)
                safe_q_text = "".join(c if c.isalnum() else "_" for c in q_text[:30]);
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S");
                filename_suffix = "final" if final else "parcial"
                if final:
                    image_filename = f"asamblea_{self.current_assembly_id}_preg_{question_id_for_results}_{safe_q_text}_{filename_suffix}.png"
                else:
                    image_filename = f"asamblea_{self.current_assembly_id}_preg_{question_id_for_results}_{safe_q_text}_{filename_suffix}_{timestamp}.png"
                filepath = os.path.join(GRAFICOS_DIR, image_filename);
                fig.savefig(filepath, bbox_inches='tight');
                print(f"Gráfico guardado: {filepath}")
            except Exception as e:
                print(f"Error guardando gráfico: {e}"); messagebox.showwarning("Error Guardar Gráfico",
                                                                               f"No se pudo guardar:\n{e}")
            figure_canvas = FigureCanvasTkAgg(fig, master=self.results_display_frame);
            self.results_canvas_widget = figure_canvas.get_tk_widget();
            self.results_canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True);
            figure_canvas.draw()
        plt.close(fig)

    # --- Pestaña Lista Votación ---
    def setup_lista_vt_tab(self):
        frame = self.lista_vt_tab;
        filter_frame = ttk.LabelFrame(frame, text="Filtros", padding=10);
        filter_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(filter_frame, text="Asamblea:").grid(row=0, column=0, padx=5, pady=5, sticky="w");
        self.lista_vt_asamblea_combo = ttk.Combobox(filter_frame, state="readonly", width=50);
        self.lista_vt_asamblea_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew");
        self.lista_vt_asamblea_combo.bind("<<ComboboxSelected>>", self.on_lista_vt_assembly_selected)
        ttk.Label(filter_frame, text="Pregunta:").grid(row=1, column=0, padx=5, pady=5, sticky="w");
        self.lista_vt_pregunta_combo = ttk.Combobox(filter_frame, state="readonly", width=50);
        self.lista_vt_pregunta_combo.grid(row=1, column=1, padx=5, pady=5, sticky="ew");
        self.lista_vt_pregunta_combo.bind("<<ComboboxSelected>>", self.load_lista_votacion_data)
        filter_frame.grid_columnconfigure(1, weight=1);
        ttk.Button(filter_frame, text="Cargar/Refrescar", command=self.load_lista_votacion_data).grid(row=1, column=2,
                                                                                                      padx=10, pady=5)
        list_frame = ttk.LabelFrame(frame, text="Detalle Votación por Unidad", padding=10);
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)
        columns = ("unidad", "coef", "propietario", "ejecuta_voto", "opcion");
        self.lista_vt_tree = ttk.Treeview(list_frame, columns=columns, show="headings");
        self.lista_vt_tree.heading("unidad", text="Unidad");
        self.lista_vt_tree.column("unidad", width=100);
        self.lista_vt_tree.heading("coef", text="Coef.");
        self.lista_vt_tree.column("coef", width=80, anchor=tk.E);
        self.lista_vt_tree.heading("propietario", text="Propietario");
        self.lista_vt_tree.column("propietario", width=200);
        self.lista_vt_tree.heading("ejecuta_voto", text="Votó (Cédula)");
        self.lista_vt_tree.column("ejecuta_voto", width=120);
        self.lista_vt_tree.heading("opcion", text="Opción Elegida");
        self.lista_vt_tree.column("opcion", width=150)
        self.lista_vt_tree.pack(side=tk.LEFT, fill="both", expand=True);
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.lista_vt_tree.yview);
        self.lista_vt_tree.configure(yscrollcommand=scrollbar.set);
        scrollbar.pack(side=tk.RIGHT, fill="y")

    def on_lista_vt_assembly_selected(self, event=None):
        self.load_questions_for_lista_vt()
        if hasattr(self, 'lista_vt_tree'):
            for i in self.lista_vt_tree.get_children(): self.lista_vt_tree.delete(i)

    def load_questions_for_lista_vt(self, event=None):
        self.lista_vt_pregunta_combo['values'] = [];
        self.lista_vt_pregunta_combo.set('')
        if hasattr(self, 'lista_vt_tree'):
            for i in self.lista_vt_tree.get_children(): self.lista_vt_tree.delete(i)
        selection = self.lista_vt_asamblea_combo.get()
        if not selection: return
        try:
            asamblea_id = int(selection.split(":")[0])
        except (ValueError, IndexError):
            return
        questions = self.execute_query("SELECT id, texto_pregunta FROM preguntas WHERE asamblea_id = ? ORDER BY id",
                                       (asamblea_id,), fetchall=True)
        if questions:
            self.lista_vt_pregunta_combo['values'] = [f"{q[0]}: {q[1]}" for q in questions]
            if questions: self.lista_vt_pregunta_combo.current(0); self.load_lista_votacion_data()

    def load_lista_votacion_data(self, event=None):
        if hasattr(self, 'lista_vt_tree'):
            for i in self.lista_vt_tree.get_children(): self.lista_vt_tree.delete(i)
        asamblea_selection = self.lista_vt_asamblea_combo.get();
        pregunta_selection = self.lista_vt_pregunta_combo.get()
        if not asamblea_selection or not pregunta_selection: return
        try:
            asamblea_id = int(asamblea_selection.split(":")[0]); pregunta_id = int(pregunta_selection.split(":")[0])
        except (ValueError, IndexError):
            return
        unidades = self.execute_query(
            """SELECT u.id_unidad, u.nombre_unidad, u.coeficiente, p.nombre FROM unidades u LEFT JOIN propietarios p ON u.cedula_propietario = p.cedula ORDER BY u.nombre_unidad""",
            fetchall=True)
        if not unidades: return
        votos = self.execute_query(
            """SELECT id_unidad_representada, cedula_ejecuta_voto, opcion_elegida FROM votos WHERE pregunta_id = ?""",
            (pregunta_id,), fetchall=True)
        votos_map = {v[0]: {'cedula': v[1], 'opcion': v[2]} for v in votos} if votos else {}
        for id_u, nom_u, coef, nom_prop in unidades:
            voto_info = votos_map.get(id_u)
            cedula_voto = voto_info['cedula'] if voto_info and voto_info['opcion'] != OPCION_NO_VOTO else "---"
            opcion_voto = voto_info['opcion'] if voto_info else OPCION_NO_VOTO
            self.lista_vt_tree.insert("", "end",
                                      values=(nom_u, f"{coef:.4f}", nom_prop or "N/A", cedula_voto, opcion_voto))

    # --- Pestaña Importar Excel ---
    def setup_import_tab(self):
        frame = self.import_tab;
        file_frame = ttk.LabelFrame(frame, text="Seleccionar Archivo Excel", padding=10);
        file_frame.pack(padx=10, pady=10, fill="x")
        ttk.Button(file_frame, text="Buscar Archivo (.xlsx, .xls)", command=self.browse_excel_file).pack(side=tk.LEFT,
                                                                                                         padx=5)
        self.excel_path_label = ttk.Label(file_frame, textvariable=self.excel_file_path, wraplength=400);
        self.excel_path_label.pack(side=tk.LEFT, padx=5, fill="x", expand=True);
        self.excel_file_path.set("Ningún archivo seleccionado")
        mapping_frame = ttk.LabelFrame(frame, text="Mapeo de Columnas Excel", padding=10);
        mapping_frame.pack(padx=10, pady=10, fill="x")
        self.col_cedula_var = tk.StringVar(value="CEDULA");
        self.col_nombre_prop_var = tk.StringVar(value="NOMBRE_PROPIETARIO");
        self.col_celular_var = tk.StringVar(value="CELULAR");
        self.col_unidad_var = tk.StringVar(value="UNIDAD");
        self.col_coeficiente_var = tk.StringVar(value="COEFICIENTE");
        self.sheet_name_var = tk.StringVar(value="")
        ttk.Label(mapping_frame, text="Nombre Hoja (opcional):").grid(row=0, column=0, padx=5, pady=3, sticky="w");
        ttk.Entry(mapping_frame, textvariable=self.sheet_name_var, width=30).grid(row=0, column=1, padx=5, pady=3,
                                                                                  sticky="ew")
        ttk.Label(mapping_frame, text="Columna Cédula Prop.:").grid(row=1, column=0, padx=5, pady=3, sticky="w");
        ttk.Entry(mapping_frame, textvariable=self.col_cedula_var, width=30).grid(row=1, column=1, padx=5, pady=3,
                                                                                  sticky="ew")
        ttk.Label(mapping_frame, text="Columna Nombre Prop.:").grid(row=2, column=0, padx=5, pady=3, sticky="w");
        ttk.Entry(mapping_frame, textvariable=self.col_nombre_prop_var, width=30).grid(row=2, column=1, padx=5, pady=3,
                                                                                       sticky="ew")
        ttk.Label(mapping_frame, text="Columna Celular Prop. (opc):").grid(row=3, column=0, padx=5, pady=3, sticky="w");
        ttk.Entry(mapping_frame, textvariable=self.col_celular_var, width=30).grid(row=3, column=1, padx=5, pady=3,
                                                                                   sticky="ew")
        ttk.Label(mapping_frame, text="Columna Nombre Unidad:").grid(row=4, column=0, padx=5, pady=3, sticky="w");
        ttk.Entry(mapping_frame, textvariable=self.col_unidad_var, width=30).grid(row=4, column=1, padx=5, pady=3,
                                                                                  sticky="ew")
        ttk.Label(mapping_frame, text="Columna Coeficiente:").grid(row=5, column=0, padx=5, pady=3, sticky="w");
        ttk.Entry(mapping_frame, textvariable=self.col_coeficiente_var, width=30).grid(row=5, column=1, padx=5, pady=3,
                                                                                       sticky="ew")
        mapping_frame.grid_columnconfigure(1, weight=1)
        action_frame = ttk.Frame(frame);
        action_frame.pack(padx=10, pady=10, fill="x");
        ttk.Button(action_frame, text="Importar Datos", command=self.import_data_from_excel).pack(pady=10)
        log_frame = ttk.LabelFrame(frame, text="Resultado Importación", padding=10);
        log_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.import_log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled");
        log_scroll = ttk.Scrollbar(log_frame, command=self.import_log_text.yview);
        self.import_log_text.config(yscrollcommand=log_scroll.set);
        self.import_log_text.pack(side=tk.LEFT, fill="both", expand=True);
        log_scroll.pack(side=tk.RIGHT, fill="y")

    def browse_excel_file(self):
        filetypes = (("Archivos Excel", "*.xlsx *.xls"), ("Todos", "*.*"));
        filepath = filedialog.askopenfilename(title="Seleccionar Excel", filetypes=filetypes)
        if filepath:
            self.excel_file_path.set(filepath); self.log_import_message(f"Archivo: {filepath}")
        else:
            self.excel_file_path.set("Ningún archivo")

    def log_import_message(self, message):
        self.import_log_text.config(state="normal");
        self.import_log_text.insert(tk.END, message + "\n");
        self.import_log_text.config(state="disabled");
        self.import_log_text.see(tk.END)

    def import_data_from_excel(self):
        if not PANDAS_AVAILABLE: messagebox.showerror("Error Librería",
                                                      "Instala 'pandas' y 'openpyxl'.\nEjecuta: pip install pandas openpyxl"); return
        filepath = self.excel_file_path.get();
        if not filepath or filepath == "Ningún archivo seleccionado": messagebox.showerror("Error",
                                                                                           "Selecciona archivo Excel."); return
        sheet = self.sheet_name_var.get().strip() or None;
        col_cedula = self.col_cedula_var.get().strip();
        col_nombre_prop = self.col_nombre_prop_var.get().strip();
        col_celular = self.col_celular_var.get().strip();
        col_unidad = self.col_unidad_var.get().strip();
        col_coef = self.col_coeficiente_var.get().strip()
        if not col_cedula or not col_nombre_prop or not col_unidad or not col_coef: messagebox.showerror("Error Mapeo",
                                                                                                         "Columnas Cédula, Nombre Prop., Unidad y Coeficiente obligatorias."); return
        self.log_import_message(f"--- Iniciando importación desde {os.path.basename(filepath)} ---")
        try:
            df = pd.read_excel(filepath, sheet_name=sheet, dtype=str);
            df = df.fillna('')
            self.log_import_message(f"Archivo leído. {len(df)} filas.");
            required_cols = {col_cedula, col_nombre_prop, col_unidad, col_coef};
            if col_celular: required_cols.add(col_celular)
            missing_cols = required_cols - set(df.columns)
            if missing_cols: messagebox.showerror("Error Columnas",
                                                  f"Columnas no encontradas: {', '.join(missing_cols)}"); self.log_import_message(
                f"ERROR: Columnas faltantes: {', '.join(missing_cols)}"); return
            conn = sqlite3.connect(DB_NAME);
            cursor = conn.cursor();
            props_added = 0;
            props_skipped = 0;
            unidades_added = 0;
            unidades_skipped = 0;
            errors = 0
            for index, row in df.iterrows():
                cedula = str(row[col_cedula]).strip();
                nombre = str(row[col_nombre_prop]).strip();
                celular = str(row[col_celular]).strip() if col_celular else "";
                unidad = str(row[col_unidad]).strip();
                coef_str = str(row[col_coef]).strip().replace(',', '.')
                if not cedula or not nombre or not unidad or not coef_str: self.log_import_message(
                    f"FILA {index + 2} OMITIDA: Faltan datos."); errors += 1; continue
                try:
                    coef = float(coef_str)
                except ValueError:
                    self.log_import_message(
                        f"FILA {index + 2} OMITIDA: Coef '{coef_str}' inválido (Unidad '{unidad}')."); errors += 1; continue
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO propietarios (cedula, nombre, celular, activo) VALUES (?, ?, ?, 1)",
                        (cedula, nombre, celular if celular else None))
                    if cursor.rowcount > 0:
                        props_added += 1
                    else:
                        props_skipped += 1
                except sqlite3.IntegrityError as e:
                    self.log_import_message(
                        f"FILA {index + 2} ERROR PROP: {e} (Céd: {cedula}, Cel: {celular})"); errors += 1; continue
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO unidades (nombre_unidad, coeficiente, cedula_propietario) VALUES (?, ?, ?)",
                        (unidad, coef, cedula))
                    if cursor.rowcount > 0:
                        unidades_added += 1
                    else:
                        unidades_skipped += 1
                except sqlite3.Error as e:
                    self.log_import_message(
                        f"FILA {index + 2} ERROR UNIDAD: {e} (Unidad: {unidad}, Céd Prop: {cedula})"); errors += 1;
            conn.commit();
            conn.close()
            summary = f"--- Fin Importación ---\nProp. Nuevos: {props_added}\nProp. Omitidos: {props_skipped}\nUnidades Nuevas: {unidades_added}\nUnidades Omitidas: {unidades_skipped}\nErrores/Omitidos: {errors}"
            self.log_import_message(summary);
            messagebox.showinfo("Importación Completa", summary);
            self.load_propietarios();
            self.load_unidades()
        except FileNotFoundError:
            messagebox.showerror("Error Archivo", f"No se encontró: {filepath}"); self.log_import_message(
                f"ERROR: Archivo no encontrado: {filepath}")
        except ImportError:
            messagebox.showerror("Error Librería",
                                 "Instala 'pandas' y 'openpyxl'.\nEjecuta: pip install pandas openpyxl"); self.log_import_message(
                "ERROR: Falta pandas u openpyxl.")
        except Exception as e:
            messagebox.showerror("Error Importación", f"Error inesperado: {e}"); self.log_import_message(
                f"ERROR INESPERADO: {e}")


# --- Main ---
if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
