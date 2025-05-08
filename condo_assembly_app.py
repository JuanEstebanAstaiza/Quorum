import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import Counter, defaultdict
import os
import datetime

# --- Configuración ---
HOST_DATA_DIR = "condominio_db_data"
DB_NAME = os.path.join(HOST_DATA_DIR, 'condominio.db')
GRAFICOS_DIR = os.path.join(HOST_DATA_DIR, 'graficos_votaciones')

# Constantes para estados de pregunta
ESTADO_PREGUNTA_INACTIVA = 'inactiva'
ESTADO_PREGUNTA_ACTIVA = 'activa'
ESTADO_PREGUNTA_CERRADA = 'cerrada'

# Constantes para tipos de residente
TIPO_RESIDENTE_REPRESENTANTE = 'representante'
TIPO_RESIDENTE_ASISTENTE = 'asistente'

# Constante para límite de inasistencias
LIMITE_INASISTENCIAS_VOTO = 3


# --- Funciones de Base de Datos e Inicialización ---
def init_app_dirs_and_db():
    # (Sin cambios)
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
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS residentes (cedula TEXT PRIMARY KEY, nombre TEXT NOT NULL, celular TEXT UNIQUE NOT NULL, casa TEXT NOT NULL, activo INTEGER DEFAULT 1, telegram_user_id INTEGER UNIQUE, tipo_residente TEXT DEFAULT 'representante', preguntas_consecutivas_sin_votar INTEGER DEFAULT 0, ultima_asamblea_actividad INTEGER)''')
    cols_to_add = {'tipo_residente': f"TEXT DEFAULT '{TIPO_RESIDENTE_REPRESENTANTE}'",
                   'preguntas_consecutivas_sin_votar': "INTEGER DEFAULT 0", 'ultima_asamblea_actividad': "INTEGER"}
    existing_cols = [col[1] for col in cursor.execute("PRAGMA table_info(residentes)").fetchall()]
    for col, col_type in cols_to_add.items():
        if col not in existing_cols:
            try:
                print(f"Añadiendo columna '{col}' a 'residentes'."); cursor.execute(
                    f"ALTER TABLE residentes ADD COLUMN {col} {col_type}"); conn.commit()
            except sqlite3.Error as e:
                print(f"Error añadiendo {col}: {e}")
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS asambleas (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, descripcion TEXT)''')
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS poderes (id INTEGER PRIMARY KEY AUTOINCREMENT, asamblea_id INTEGER NOT NULL, cedula_da_poder TEXT NOT NULL, cedula_recibe_poder TEXT NOT NULL, FOREIGN KEY (asamblea_id) REFERENCES asambleas(id), FOREIGN KEY (cedula_da_poder) REFERENCES residentes(cedula), FOREIGN KEY (cedula_recibe_poder) REFERENCES residentes(cedula), UNIQUE (asamblea_id, cedula_da_poder))''')
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS preguntas (id INTEGER PRIMARY KEY AUTOINCREMENT, asamblea_id INTEGER NOT NULL, texto_pregunta TEXT NOT NULL, opciones_configuradas TEXT, estado TEXT DEFAULT 'inactiva', FOREIGN KEY (asamblea_id) REFERENCES asambleas(id))''')
    try:
        cursor.execute("SELECT activa FROM preguntas LIMIT 1"); print(
            "Migrando 'activa' a 'estado' en 'preguntas'."); cursor.execute(
            "ALTER TABLE preguntas RENAME COLUMN activa TO estado_old_int"); cursor.execute(
            f"ALTER TABLE preguntas ADD COLUMN estado TEXT DEFAULT '{ESTADO_PREGUNTA_INACTIVA}'"); cursor.execute(
            f"UPDATE preguntas SET estado = '{ESTADO_PREGUNTA_ACTIVA}' WHERE estado_old_int = 1"); cursor.execute(
            f"UPDATE preguntas SET estado = '{ESTADO_PREGUNTA_CERRADA}' WHERE estado_old_int = 0"); cursor.execute(
            "ALTER TABLE preguntas DROP COLUMN estado_old_int"); conn.commit(); print("Migración completada.")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("SELECT estado FROM preguntas LIMIT 1")
    except sqlite3.OperationalError:
        print("Añadiendo 'estado' a 'preguntas'."); cursor.execute(
            f"ALTER TABLE preguntas ADD COLUMN estado TEXT DEFAULT '{ESTADO_PREGUNTA_INACTIVA}'"); conn.commit()
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS votos (id INTEGER PRIMARY KEY AUTOINCREMENT, pregunta_id INTEGER NOT NULL, cedula_votante TEXT NOT NULL, opcion_elegida TEXT NOT NULL, FOREIGN KEY (pregunta_id) REFERENCES preguntas(id), FOREIGN KEY (cedula_votante) REFERENCES residentes(cedula), UNIQUE (pregunta_id, cedula_votante))''')
    conn.commit();
    conn.close()


# --- Clases de la Aplicación ---
class App:
    # ... ( __init__ y execute_query sin cambios) ...
    def __init__(self, root):
        self.root = root;
        self.root.title("Gestión de Asambleas");
        self.root.geometry("1150x800")
        style = ttk.Style();
        style.theme_use('clam')
        self.current_assembly_id = None;
        self.current_question_id = None
        self.current_question_options = [];
        self.editing_question_id = None
        self.notebook = ttk.Notebook(root)
        self.resident_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.resident_tab, text='Residentes');
        self.setup_resident_tab()
        self.assembly_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.assembly_tab, text='Asambleas');
        self.setup_assembly_tab()
        self.voting_tab = ttk.Frame(self.notebook);
        self.notebook.add(self.voting_tab, text='Votación');
        self.setup_voting_tab()
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)
        init_app_dirs_and_db();
        self.load_residents();
        self.load_assemblies()

    def execute_query(self, query, params=(), fetchone=False, fetchall=False, commit=False):
        conn = sqlite3.connect(DB_NAME);
        cursor = conn.cursor()
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

    # --- Pestaña de Residentes (sin cambios) ---
    def setup_resident_tab(self):
        frame = self.resident_tab;
        form_frame = ttk.LabelFrame(frame, text="Registrar/Actualizar Residente", padding=10);
        form_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(form_frame, text="Cédula:").grid(row=0, column=0, padx=5, pady=5, sticky="w");
        self.resident_cedula_entry = ttk.Entry(form_frame, width=40);
        self.resident_cedula_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(form_frame, text="Nombre:").grid(row=1, column=0, padx=5, pady=5, sticky="w");
        self.resident_name_entry = ttk.Entry(form_frame, width=40);
        self.resident_name_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(form_frame, text="Celular:").grid(row=2, column=0, padx=5, pady=5, sticky="w");
        self.resident_phone_entry = ttk.Entry(form_frame, width=40);
        self.resident_phone_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(form_frame, text="Casa/Apto:").grid(row=3, column=0, padx=5, pady=5, sticky="w");
        self.resident_house_entry = ttk.Entry(form_frame, width=40);
        self.resident_house_entry.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(form_frame, text="Tipo:").grid(row=4, column=0, padx=5, pady=5, sticky="w");
        self.resident_type_var = tk.StringVar();
        self.resident_type_combobox = ttk.Combobox(form_frame, textvariable=self.resident_type_var,
                                                   values=[TIPO_RESIDENTE_REPRESENTANTE.capitalize(),
                                                           TIPO_RESIDENTE_ASISTENTE.capitalize()], state="readonly",
                                                   width=38);
        self.resident_type_combobox.grid(row=4, column=1, padx=5, pady=5, sticky="ew");
        self.resident_type_combobox.set(TIPO_RESIDENTE_REPRESENTANTE.capitalize())
        self.resident_cedula_to_update = None
        button_frame = ttk.Frame(form_frame);
        button_frame.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text="Guardar Residente", command=self.save_resident).pack(side=tk.LEFT, padx=5);
        ttk.Button(button_frame, text="Limpiar Campos", command=self.clear_resident_fields).pack(side=tk.LEFT, padx=5)
        list_frame = ttk.LabelFrame(frame, text="Lista de Residentes (Activos e Inactivos)", padding=10);
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)
        columns = ("cedula", "nombre", "tipo", "estado_act", "ausencias", "celular", "casa")
        self.resident_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self.resident_tree.heading("cedula", text="Cédula");
        self.resident_tree.column("cedula", width=90, anchor=tk.W)
        self.resident_tree.heading("nombre", text="Nombre");
        self.resident_tree.column("nombre", width=200, anchor=tk.W)
        self.resident_tree.heading("tipo", text="Tipo");
        self.resident_tree.column("tipo", width=90, anchor=tk.W)
        self.resident_tree.heading("estado_act", text="Estado");
        self.resident_tree.column("estado_act", width=70, anchor=tk.W)
        self.resident_tree.heading("ausencias", text="Aus Voto");
        self.resident_tree.column("ausencias", width=60, anchor=tk.CENTER)
        self.resident_tree.heading("celular", text="Celular");
        self.resident_tree.column("celular", width=90, anchor=tk.W)
        self.resident_tree.heading("casa", text="Casa/Apto");
        self.resident_tree.column("casa", width=70, anchor=tk.W)
        self.resident_tree.pack(fill="both", expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.resident_tree.yview);
        self.resident_tree.configure(yscrollcommand=scrollbar.set);
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.resident_tree.bind("<<TreeviewSelect>>", self.on_resident_select)
        resident_actions_frame = ttk.Frame(list_frame);
        resident_actions_frame.pack(pady=5, fill="x")
        ttk.Button(resident_actions_frame, text="Activar/Desactivar", command=self.toggle_resident_activation).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(resident_actions_frame, text="Refrescar", command=self.load_residents).pack(side=tk.LEFT, padx=5)

    def clear_resident_fields(self):
        self.resident_cedula_entry.config(state='normal');
        self.resident_cedula_entry.delete(0, tk.END)
        self.resident_name_entry.delete(0, tk.END);
        self.resident_phone_entry.delete(0, tk.END);
        self.resident_house_entry.delete(0, tk.END)
        self.resident_type_combobox.set(TIPO_RESIDENTE_REPRESENTANTE.capitalize());
        self.resident_cedula_to_update = None;
        self.resident_cedula_entry.focus()

    def save_resident(self):
        cedula = self.resident_cedula_entry.get().strip();
        nombre = self.resident_name_entry.get().strip();
        celular = self.resident_phone_entry.get().strip();
        casa = self.resident_house_entry.get().strip();
        tipo_residente_ui = self.resident_type_var.get().lower()
        if not cedula or not nombre or not celular or not casa or not tipo_residente_ui: messagebox.showerror("Error",
                                                                                                              "Todos los campos obligatorios."); return
        if tipo_residente_ui not in [TIPO_RESIDENTE_REPRESENTANTE, TIPO_RESIDENTE_ASISTENTE]: messagebox.showerror(
            "Error", f"Tipo inválido: {tipo_residente_ui}"); return
        if tipo_residente_ui == TIPO_RESIDENTE_REPRESENTANTE:
            query = "SELECT cedula, nombre FROM residentes WHERE casa = ? AND tipo_residente = ? AND activo = 1"
            params = [casa, TIPO_RESIDENTE_REPRESENTANTE]
            if self.resident_cedula_to_update: query += " AND cedula != ?"; params.append(
                self.resident_cedula_to_update)
            existing_rep = self.execute_query(query, tuple(params), fetchone=True)
            if existing_rep: messagebox.showerror("Error Representante",
                                                  f"Ya existe rep. activo ('{existing_rep[1]}', Céd: {existing_rep[0]}) para unidad '{casa}'.\nSolo 1 rep. por unidad."); return
        try:
            if self.resident_cedula_to_update:
                self.execute_query("UPDATE residentes SET nombre=?, celular=?, casa=?, tipo_residente=? WHERE cedula=?",
                                   (nombre, celular, casa, tipo_residente_ui, self.resident_cedula_to_update),
                                   commit=True)
                messagebox.showinfo("Éxito", "Residente actualizado.");
            else:
                self.execute_query(
                    "INSERT INTO residentes (cedula, nombre, celular, casa, tipo_residente, activo) VALUES (?, ?, ?, ?, ?, 1)",
                    (cedula, nombre, celular, casa, tipo_residente_ui), commit=True)
                messagebox.showinfo("Éxito", "Residente registrado.");
            self.clear_resident_fields();
            self.load_residents()
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: residentes.cedula" in str(e):
                messagebox.showerror("Duplicado", f"Cédula '{cedula}' ya existe.")
            elif "UNIQUE constraint failed: residentes.celular" in str(e):
                messagebox.showerror("Duplicado", f"Celular '{celular}' ya existe.")
            else:
                messagebox.showerror("Error DB", f"Error: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Error inesperado: {e}")

    def on_resident_select(self, event=None):
        selected_item = self.resident_tree.focus();
        if not selected_item: return
        values = self.resident_tree.item(selected_item, "values")
        if values:
            self.resident_cedula_to_update = values[0];
            self.resident_cedula_entry.config(state='normal');
            self.resident_cedula_entry.delete(0, tk.END);
            self.resident_cedula_entry.insert(0, values[0]);
            self.resident_cedula_entry.config(state='disabled')
            self.resident_name_entry.delete(0, tk.END);
            self.resident_name_entry.insert(0, values[1])
            self.resident_type_combobox.set(values[2].capitalize())
            self.resident_phone_entry.delete(0, tk.END);
            self.resident_phone_entry.insert(0, values[5])
            self.resident_house_entry.delete(0, tk.END);
            self.resident_house_entry.insert(0, values[6])

    def load_residents(self):
        for i in self.resident_tree.get_children(): self.resident_tree.delete(i)
        rows = self.execute_query(
            "SELECT cedula, nombre, tipo_residente, activo, preguntas_consecutivas_sin_votar, celular, casa FROM residentes ORDER BY activo DESC, nombre",
            fetchall=True)
        if rows is not None:
            for row in rows:
                cedula, nombre, tipo, activo_int, ausencias, celular, casa = row
                estado_str = "Activo" if activo_int == 1 else "Inactivo"
                self.resident_tree.insert("", "end", values=(
                cedula, nombre, tipo.capitalize(), estado_str, ausencias, celular, casa))
        self.update_resident_comboboxes()

    def update_resident_comboboxes(self):
        residents_data = self.execute_query(
            "SELECT cedula, nombre, casa FROM residentes WHERE activo = 1 ORDER BY nombre", fetchall=True)
        resident_list = [f"{r[0]}: {r[1]} ({r[2]})" for r in residents_data] if residents_data else []
        if hasattr(self, 'proxy_giver_combobox'): self.proxy_giver_combobox[
            'values'] = resident_list; self.proxy_giver_combobox.set('')
        if hasattr(self, 'proxy_receiver_combobox'): self.proxy_receiver_combobox[
            'values'] = resident_list; self.proxy_receiver_combobox.set('')

    def toggle_resident_activation(self):
        selected_item = self.resident_tree.focus()
        if not selected_item: messagebox.showwarning("Advertencia", "Seleccione residente."); return
        values = self.resident_tree.item(selected_item, "values");
        cedula_residente = values[0];
        nombre_residente = values[1];
        estado_actual_str = values[3]
        nuevo_estado_int = 0 if estado_actual_str == "Activo" else 1;
        accion_str = "desactivar" if nuevo_estado_int == 0 else "activar"
        reset_ausencias = ", preguntas_consecutivas_sin_votar = 0" if nuevo_estado_int == 1 else ""
        if messagebox.askyesno(f"Confirmar {accion_str.capitalize()}",
                               f"¿{accion_str} a '{nombre_residente}' ({cedula_residente})?"):
            try:
                self.execute_query(f"UPDATE residentes SET activo = ? {reset_ausencias} WHERE cedula=?",
                                   (nuevo_estado_int, cedula_residente), commit=True)
                messagebox.showinfo("Éxito", f"Residente '{nombre_residente}' {accion_str}do.")
                self.load_residents();
                self.clear_resident_fields()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo actualizar: {e}")

    # --- Pestaña de Asambleas ---
    def setup_assembly_tab(self):
        # (UI sin cambios)
        frame = self.assembly_tab;
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
        ttk.Label(powers_frame, text="Da poder:").grid(row=0, column=0, padx=5, pady=5, sticky="w");
        self.proxy_giver_combobox = ttk.Combobox(powers_frame, state="readonly", width=40);
        self.proxy_giver_combobox.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(powers_frame, text="Recibe poder:").grid(row=1, column=0, padx=5, pady=5, sticky="w");
        self.proxy_receiver_combobox = ttk.Combobox(powers_frame, state="readonly", width=40);
        self.proxy_receiver_combobox.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(powers_frame, text="Asignar Poder", command=self.assign_proxy).grid(row=2, column=0, columnspan=2,
                                                                                       pady=10)
        self.powers_tree = ttk.Treeview(powers_frame, columns=("id_poder", "da_poder_cedula", "recibe_poder_cedula"),
                                        show="headings", height=4);
        self.powers_tree.heading("id_poder", text="ID");
        self.powers_tree.heading("da_poder_cedula", text="Da Poder (Cédula - Nombre)");
        self.powers_tree.heading("recibe_poder_cedula", text="Recibe Poder (Cédula - Nombre)");
        self.powers_tree.column("id_poder", width=30, anchor=tk.W);
        self.powers_tree.column("da_poder_cedula", width=250, anchor=tk.W);
        self.powers_tree.column("recibe_poder_cedula", width=250, anchor=tk.W);
        self.powers_tree.grid(row=3, column=0, columnspan=2, pady=5, sticky="ew");
        ttk.Button(powers_frame, text="Eliminar Poder", command=self.delete_proxy).grid(row=4, column=0, columnspan=2,
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
        # (Sin cambios)
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
        # (Sin cambios)
        self.editing_question_id = None;
        self.question_text_entry.config(state='normal');
        self.question_options_entry.config(state='normal')
        self.question_text_entry.delete(0, tk.END);
        self.question_options_entry.delete(0, tk.END);
        self.question_options_entry.insert(0, "Acepta,No Acepta,En Blanco")
        if self.questions_tree.focus(): self.questions_tree.selection_remove(self.questions_tree.focus())

    def on_question_select(self, event=None):
        # (Sin cambios)
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
        # (Sin cambios)
        for i in self.questions_tree.get_children(): self.questions_tree.delete(i)
        if not self.current_assembly_id: return
        questions_data = self.execute_query(
            "SELECT id, texto_pregunta, opciones_configuradas, estado FROM preguntas WHERE asamblea_id = ? ORDER BY id",
            (self.current_assembly_id,), fetchall=True)
        if questions_data:
            for q_id, q_text, q_opts, q_estado in questions_data: self.questions_tree.insert("", "end", values=(
            q_id, q_text, q_opts, q_estado.capitalize()))

    def create_assembly(self):
        # (Sin cambios)
        fecha = self.assembly_date_entry.get();
        descripcion = self.assembly_desc_entry.get()
        if not fecha or not descripcion: messagebox.showerror("Error", "Fecha y descripción obligatorias."); return
        try:
            self.execute_query("INSERT INTO asambleas (fecha, descripcion) VALUES (?, ?)", (fecha, descripcion),
                               commit=True); messagebox.showinfo("Éxito",
                                                                 "Asamblea creada."); self.load_assemblies(); self.assembly_date_entry.delete(
                0, tk.END); self.assembly_desc_entry.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear asamblea: {e}")

    def load_assemblies(self):
        # (Sin cambios)
        assemblies = self.execute_query("SELECT id, fecha, descripcion FROM asambleas ORDER BY fecha DESC, id DESC",
                                        fetchall=True)
        if assemblies is not None:
            self.assembly_combobox['values'] = [f"{row[0]}: {row[1]} - {row[2]}" for row in assemblies]
            if assemblies:
                self.assembly_combobox.current(0); self.on_assembly_selected()
            else:
                self.assembly_combobox.set(''); self.current_assembly_id = None; self.clear_assembly_details()
        else:
            self.assembly_combobox['values'] = []; self.assembly_combobox.set(
                ''); self.current_assembly_id = None; self.clear_assembly_details()

    def clear_assembly_details(self):
        # (Sin cambios)
        if hasattr(self, 'proxy_giver_combobox'): self.proxy_giver_combobox.set('')
        if hasattr(self, 'proxy_receiver_combobox'): self.proxy_receiver_combobox.set('')
        if hasattr(self, 'powers_tree'):
            for i in self.powers_tree.get_children(): self.powers_tree.delete(i)
        if hasattr(self, 'question_text_entry'): self.question_text_entry.delete(0, tk.END)
        if hasattr(self, 'question_options_entry'):
            self.question_options_entry.delete(0, tk.END);
            self.question_options_entry.insert(0, "Acepta,No Acepta,En Blanco")
        if hasattr(self, 'questions_tree'):
            for i in self.questions_tree.get_children(): self.questions_tree.delete(i)
        self.clear_voting_area()

    def on_assembly_selected(self, event=None):
        # (Sin cambios)
        selection = self.assembly_combobox.get()
        if selection:
            try:
                self.current_assembly_id = int(selection.split(":")[0]); self.load_selected_assembly_details()
            except ValueError:
                messagebox.showerror("Error",
                                     "Selección inválida."); self.current_assembly_id = None; self.clear_assembly_details()
        else:
            self.current_assembly_id = None; self.clear_assembly_details()

    def load_selected_assembly_details(self):
        # (Sin cambios)
        if not self.current_assembly_id: self.clear_assembly_details(); return
        self.execute_query(
            "UPDATE residentes SET preguntas_consecutivas_sin_votar = 0 WHERE ultima_asamblea_actividad != ? OR ultima_asamblea_actividad IS NULL",
            (self.current_assembly_id,), commit=True)
        self.update_resident_comboboxes();
        self.load_proxies_for_assembly();
        self.load_questions_for_assembly();
        self.load_questions_for_voting_tab()

    def assign_proxy(self):
        """Asigna poder, verificando que quien da poder sea Representante."""
        if not self.current_assembly_id: messagebox.showerror("Error", "Seleccione asamblea."); return
        giver_selection = self.proxy_giver_combobox.get();
        receiver_selection = self.proxy_receiver_combobox.get()
        if not giver_selection or not receiver_selection: messagebox.showerror("Error",
                                                                               "Seleccione ambos residentes."); return

        try:
            cedula_da_poder = giver_selection.split(":")[0].strip()
            cedula_recibe_poder = receiver_selection.split(":")[0].strip()

            if cedula_da_poder == cedula_recibe_poder: messagebox.showerror("Error",
                                                                            "No puede darse poder a sí mismo."); return

            # --- NUEVA VERIFICACIÓN: Solo Representantes dan poder ---
            giver_info = self.execute_query("SELECT tipo_residente FROM residentes WHERE cedula = ? AND activo = 1",
                                            (cedula_da_poder,), fetchone=True)
            if not giver_info:
                messagebox.showerror("Error", f"Residente '{giver_selection}' no encontrado o inactivo.");
                return
            if giver_info[0] != TIPO_RESIDENTE_REPRESENTANTE:
                messagebox.showerror("Error de Poder",
                                     f"'{giver_selection.split(':')[1].strip()}' es '{giver_info[0].capitalize()}' y no puede dar poder. Solo los representantes pueden.")
                return
            # --- FIN VERIFICACIÓN ---

            self.execute_query(
                "INSERT INTO poderes (asamblea_id, cedula_da_poder, cedula_recibe_poder) VALUES (?, ?, ?)",
                (self.current_assembly_id, cedula_da_poder, cedula_recibe_poder), commit=True)
            messagebox.showinfo("Éxito", "Poder asignado.");
            self.load_proxies_for_assembly();
            if self.current_question_id: self.load_eligible_voters()  # Actualizar lista de votantes
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Este residente ya otorgó poder en esta asamblea.");
        except ValueError:
            messagebox.showerror("Error", "Selección inválida.");
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo asignar: {e}")

    def load_proxies_for_assembly(self):
        # (Sin cambios)
        for i in self.powers_tree.get_children(): self.powers_tree.delete(i)
        if not self.current_assembly_id: return
        query = """SELECT p.id, r1.cedula || ': ' || r1.nombre, r2.cedula || ': ' || r2.nombre FROM poderes p JOIN residentes r1 ON p.cedula_da_poder = r1.cedula JOIN residentes r2 ON p.cedula_recibe_poder = r2.cedula WHERE p.asamblea_id = ? AND r1.activo = 1 AND r2.activo = 1"""
        proxies = self.execute_query(query, (self.current_assembly_id,), fetchall=True)
        if proxies:
            for p_data in proxies: self.powers_tree.insert("", "end", values=p_data)

    def delete_proxy(self):
        # (Sin cambios)
        selected_item = self.powers_tree.focus();
        if not selected_item: messagebox.showwarning("Advertencia", "Seleccione poder."); return
        if not self.current_assembly_id: messagebox.showerror("Error", "No hay asamblea."); return
        if messagebox.askyesno("Confirmar", "¿Eliminar poder?"):
            power_id = self.powers_tree.item(selected_item, "values")[0]
            try:
                self.execute_query("DELETE FROM poderes WHERE id=? AND asamblea_id=?",
                                   (power_id, self.current_assembly_id), commit=True); messagebox.showinfo("Éxito",
                                                                                                           "Poder eliminado."); self.load_proxies_for_assembly();
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar: {e}")

    # --- Pestaña de Votación ---
    # (setup_voting_tab, load_questions_for_voting_tab, clear_voting_area, on_voting_question_selected_for_display, update_vote_options_ui, activate_question_for_voting sin cambios)
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
        if q_info[0] != ESTADO_PREGUNTA_INACTIVA: messagebox.showwarning("Advertencia",
                                                                         f"Pregunta ya está '{q_info[0].capitalize()}'."); return
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
        self.load_eligible_voters();
        self.display_vote_results_for_question(self.current_question_id);
        self.load_questions_for_assembly()
        messagebox.showinfo("Votación Activada", f"Pregunta '{question_text}' activa.")

    def close_current_question_voting(self):
        # (Sin cambios)
        if not self.current_question_id: messagebox.showwarning("Advertencia", "Ninguna pregunta activa."); return
        question_id_to_close = self.current_question_id
        q_info = self.execute_query("SELECT texto_pregunta FROM preguntas WHERE id = ?", (question_id_to_close,),
                                    fetchone=True);
        question_text_closed = q_info[0] if q_info else f"ID {question_id_to_close}"
        deactivated_residents = self.check_and_deactivate_non_voters(question_id_to_close)
        if deactivated_residents: messagebox.showinfo("Residentes Desactivados",
                                                      f"Desactivados por {LIMITE_INASISTENCIAS_VOTO} ausencias:\n- " + "\n- ".join(
                                                          deactivated_residents)); self.load_residents()
        self.execute_query("UPDATE preguntas SET estado = ? WHERE id = ?",
                           (ESTADO_PREGUNTA_CERRADA, question_id_to_close,), commit=True);
        self.load_questions_for_assembly()
        messagebox.showinfo("Votación Cerrada", f"Se cerró votación para: '{question_text_closed}'.");
        self.display_vote_results_for_question(question_id_to_close, final=True)
        self.current_question_id = None;
        self.current_question_options = []
        self.active_question_label.config(text="Pregunta Activa: Ninguna");
        self.voting_resident_combobox.set('');
        self.voting_resident_combobox['values'] = [];
        self.vote_option_var_string.set("")
        if hasattr(self, 'options_radio_frame') and self.options_radio_frame.winfo_exists():
            for widget in self.options_radio_frame.winfo_children(): widget.destroy()

    def check_and_deactivate_non_voters(self, closed_question_id):
        # (Sin cambios)
        if not self.current_assembly_id: return []
        eligible_cedulas = self._get_eligible_voter_cedulas()
        if not eligible_cedulas: return []
        voters_cedulas = {row[0] for row in self.execute_query("SELECT cedula_votante FROM votos WHERE pregunta_id = ?",
                                                               (closed_question_id,), fetchall=True) or []}
        resident_inactivity_data = self.execute_query(
            f"SELECT cedula, preguntas_consecutivas_sin_votar, ultima_asamblea_actividad FROM residentes WHERE cedula IN ({','.join('?' * len(eligible_cedulas))})",
            list(eligible_cedulas), fetchall=True)
        if not resident_inactivity_data: return []
        inactivity_map = {row[0]: {'count': row[1], 'last_assembly': row[2]} for row in resident_inactivity_data}
        deactivated_list = [];
        updates_to_make = []
        for cedula in eligible_cedulas:
            current_data = inactivity_map.get(cedula, {'count': 0, 'last_assembly': None});
            current_count = current_data['count'];
            last_assembly = current_data['last_assembly']
            if cedula in voters_cedulas:
                if current_count > 0 or last_assembly != self.current_assembly_id: updates_to_make.append(
                    (cedula, 0, self.current_assembly_id, 1))
            else:
                new_count = current_count + 1 if last_assembly == self.current_assembly_id else 1
                new_active_status = 0 if new_count >= LIMITE_INASISTENCIAS_VOTO else 1
                if new_active_status == 0: res_name = self.execute_query(
                    "SELECT nombre FROM residentes WHERE cedula = ?", (cedula,),
                    fetchone=True); deactivated_list.append(f"{res_name[0] if res_name else '??'} ({cedula})"); print(
                    f"INFO: Residente {cedula} desactivado.")
                updates_to_make.append((cedula, new_count, self.current_assembly_id, new_active_status))
        if updates_to_make:
            conn = sqlite3.connect(DB_NAME);
            cursor = conn.cursor()
            try:
                cursor.executemany(
                    "UPDATE residentes SET preguntas_consecutivas_sin_votar = ?, ultima_asamblea_actividad = ?, activo = ? WHERE cedula = ?",
                    [(upd[1], upd[2], upd[3], upd[0]) for upd in updates_to_make]); conn.commit(); print(
                    f"INFO: Actualizado estado inasistencia para {len(updates_to_make)}.")
            except sqlite3.Error as e:
                print(f"ERROR actualizando inasistencias: {e}"); conn.rollback()
            finally:
                conn.close()
        return deactivated_list

    def _get_eligible_voter_cedulas(self):
        # (Lógica actualizada para 1 voto/unidad)
        if not self.current_assembly_id: return set()
        all_residents = self.execute_query("SELECT cedula, tipo_residente, casa FROM residentes WHERE activo = 1",
                                           fetchall=True)
        if not all_residents: return set()
        cedulas_dieron_poder = {row[0] for row in
                                self.execute_query("SELECT cedula_da_poder FROM poderes WHERE asamblea_id = ?",
                                                   (self.current_assembly_id,), fetchall=True) or []}
        cedulas_recibieron_poder = {row[0] for row in
                                    self.execute_query("SELECT cedula_recibe_poder FROM poderes WHERE asamblea_id = ?",
                                                       (self.current_assembly_id,), fetchall=True) or []}
        eligible_cedulas = set();
        casas_con_representante_elegible = set()
        for cedula, tipo, casa in all_residents:
            if cedula in cedulas_dieron_poder: continue
            if tipo == TIPO_RESIDENTE_REPRESENTANTE and casa not in casas_con_representante_elegible:
                eligible_cedulas.add(cedula);
                casas_con_representante_elegible.add(casa)
        for cedula, tipo, casa in all_residents:
            if cedula in cedulas_dieron_poder: continue
            if tipo == TIPO_RESIDENTE_ASISTENTE and cedula in cedulas_recibieron_poder:
                if casa not in casas_con_representante_elegible and cedula not in eligible_cedulas:
                    eligible_cedulas.add(cedula)
        return eligible_cedulas

    def load_eligible_voters(self):
        # (Sin cambios)
        self.voting_resident_combobox['values'] = [];
        self.voting_resident_combobox.set('')
        if not self.current_assembly_id: return
        eligible_cedulas = self._get_eligible_voter_cedulas()
        if not eligible_cedulas: return
        eligible_details = self.execute_query(
            f"SELECT cedula, nombre, casa FROM residentes WHERE cedula IN ({','.join('?' * len(eligible_cedulas))}) ORDER BY nombre",
            list(eligible_cedulas), fetchall=True)
        eligible_voters_list = [f"{r[0]}: {r[1]} ({r[2]})" for r in eligible_details] if eligible_details else []
        self.voting_resident_combobox['values'] = eligible_voters_list
        if eligible_voters_list:
            self.voting_resident_combobox.current(0)
        else:
            self.voting_resident_combobox.set('')

    def register_vote(self):
        # (Sin cambios)
        if not self.current_question_id: messagebox.showerror("Error", "Ninguna pregunta activa."); return
        voter_selection = self.voting_resident_combobox.get();
        opcion_elegida_str = self.vote_option_var_string.get()
        if not voter_selection: messagebox.showerror("Error", "Seleccione votante."); return
        if not opcion_elegida_str: messagebox.showerror("Error", "Seleccione opción."); return
        try:
            cedula_votante = voter_selection.split(":")[0].strip()
            existing_vote = self.execute_query("SELECT id FROM votos WHERE pregunta_id = ? AND cedula_votante = ?",
                                               (self.current_question_id, cedula_votante), fetchone=True)
            if existing_vote:
                if messagebox.askyesno("Confirmar Cambio", "Ya votó. ¿Cambiar voto?"):
                    self.execute_query(
                        "UPDATE votos SET opcion_elegida = ? WHERE pregunta_id = ? AND cedula_votante = ?",
                        (opcion_elegida_str, self.current_question_id, cedula_votante), commit=True);
                    messagebox.showinfo("Éxito", "Voto actualizado.")
                else:
                    return
            else:
                self.execute_query("INSERT INTO votos (pregunta_id, cedula_votante, opcion_elegida) VALUES (?, ?, ?)",
                                   (self.current_question_id, cedula_votante, opcion_elegida_str), commit=True);
                messagebox.showinfo("Éxito", "Voto registrado.")
            self.execute_query(
                "UPDATE residentes SET preguntas_consecutivas_sin_votar = 0, ultima_asamblea_actividad = ? WHERE cedula = ?",
                (self.current_assembly_id, cedula_votante), commit=True)
            self.display_vote_results_for_question(self.current_question_id);
            self.vote_option_var_string.set("")
        except ValueError:
            messagebox.showerror("Error", "Selección inválida.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar: {e}")

    def get_voting_weights(self):
        # (Lógica actualizada para 1 voto/unidad + poderes)
        if not self.current_assembly_id: return {}
        weights = {};
        all_residents_info = self.execute_query("SELECT cedula, tipo_residente, casa FROM residentes WHERE activo = 1",
                                                fetchall=True)
        if not all_residents_info: return {}
        cedulas_dieron_poder = {row[0] for row in
                                self.execute_query("SELECT cedula_da_poder FROM poderes WHERE asamblea_id = ?",
                                                   (self.current_assembly_id,), fetchall=True) or []}
        casas_con_representante_asignado = set()
        for cedula, tipo, casa in all_residents_info:
            if cedula not in cedulas_dieron_poder:
                if tipo == TIPO_RESIDENTE_REPRESENTANTE and casa not in casas_con_representante_asignado:
                    weights[cedula] = 1;
                    casas_con_representante_asignado.add(casa)
                elif tipo == TIPO_RESIDENTE_ASISTENTE:
                    weights[cedula] = 0
        proxies_received = self.execute_query(
            """SELECT cedula_recibe_poder, COUNT(cedula_da_poder) FROM poderes WHERE asamblea_id = ? GROUP BY cedula_recibe_poder""",
            (self.current_assembly_id,), fetchall=True)
        if proxies_received:
            for receiver_cedula, count in proxies_received:
                if receiver_cedula in weights: weights[receiver_cedula] += count
        return weights

    def display_vote_results_for_question(self, question_id_for_results, final=False):
        # (Sin cambios)
        if not self.current_assembly_id: messagebox.showwarning("Advertencia",
                                                                "No hay asamblea."); self.clear_voting_area(); return
        if not question_id_for_results: self.clear_voting_area(); return
        if hasattr(self,
                   'results_canvas_widget') and self.results_canvas_widget: self.results_canvas_widget.destroy(); self.results_canvas_widget = None
        if hasattr(self, 'results_display_frame') and self.results_display_frame.winfo_exists():
            for widget in self.results_display_frame.winfo_children(): widget.destroy()
        votes_data = self.execute_query("SELECT cedula_votante, opcion_elegida FROM votos WHERE pregunta_id = ?",
                                        (question_id_for_results,), fetchall=True)
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
        if not votes_data:
            if hasattr(self.results_display_frame,
                       'winfo_exists') and self.results_display_frame.winfo_exists(): ttk.Label(
                self.results_display_frame, text=f"Sin votos para:\n'{q_text}'").pack(pady=20)
            return
        voting_weights_for_assembly = self.get_voting_weights();
        weighted_results = Counter()
        for cedula_votante, opcion_elegida_text in votes_data: weight_of_this_voter_event = voting_weights_for_assembly.get(
            cedula_votante, 0); weighted_results[opcion_elegida_text] += weight_of_this_voter_event
        total_weighted_votes_cast = sum(weighted_results.values());
        chart_labels = [];
        chart_sizes = [];
        raw_counts_display = Counter()
        for option_text_label in q_options_list:
            total_weight_for_option = weighted_results[option_text_label];
            count_for_option = sum(1 for _, o_elegida in votes_data if o_elegida == option_text_label);
            raw_counts_display[option_text_label] = count_for_option
            percentage = (
                                     total_weight_for_option / total_weighted_votes_cast) * 100 if total_weighted_votes_cast > 0 else 0;
            chart_labels.append(f"{option_text_label}\n({total_weight_for_option} p, {percentage:.1f}%)");
            chart_sizes.append(total_weight_for_option)
        if not chart_sizes or all(s == 0 for s in chart_sizes):
            if hasattr(self.results_display_frame,
                       'winfo_exists') and self.results_display_frame.winfo_exists(): ttk.Label(
                self.results_display_frame, text=f"Sin votos válidos:\n'{q_text}'").pack(pady=20)
            return
        fig, ax = plt.subplots(figsize=(6, 4.5));
        wedges, _, autotexts = ax.pie(chart_sizes, labels=None, autopct=lambda p: '{:.1f}%'.format(p) if p > 0 else '',
                                      startangle=90, pctdistance=0.85, wedgeprops=dict(width=0.4));
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
        info_text_lines.append("\nConteo (votantes):");
        for opt_text, count in raw_counts_display.items(): info_text_lines.append(f"- {opt_text}: {count}")
        info_text_lines.append(f"\nTotal peso emitido: {total_weighted_votes_cast}");
        total_possible_weight_in_assembly = sum(voting_weights_for_assembly.values());
        info_text_lines.append(f"Total peso posible: {total_possible_weight_in_assembly}")
        if total_possible_weight_in_assembly > 0: participation = (
                                                                              total_weighted_votes_cast / total_possible_weight_in_assembly) * 100; info_text_lines.append(
            f"Participación: {participation:.1f}%")
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


# --- Main ---
if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
