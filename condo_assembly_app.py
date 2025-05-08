import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import Counter
import os

# --- Configuración de la Base de Datos ---
HOST_DATA_DIR = "condominio_db_data"
DB_NAME = os.path.join(HOST_DATA_DIR, 'condominio.db')


# --- Funciones de Base de Datos ---
def init_db():
    """Inicializa la base de datos y crea las tablas si no existen."""
    if not os.path.exists(HOST_DATA_DIR):
        try:
            os.makedirs(HOST_DATA_DIR)
            print(f"Directorio de datos del host creado en: {HOST_DATA_DIR}")
        except OSError as e:
            print(f"Error al crear el directorio de datos del host {HOST_DATA_DIR}: {e}")
            raise

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Tabla de residentes
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS residentes (
        cedula TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        celular TEXT UNIQUE NOT NULL,
        casa TEXT NOT NULL,
        activo INTEGER DEFAULT 1
    )
    ''')

    # Tabla de asambleas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS asambleas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        descripcion TEXT
    )
    ''')

    # Tabla de poderes
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS poderes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asamblea_id INTEGER NOT NULL,
        cedula_da_poder TEXT NOT NULL,
        cedula_recibe_poder TEXT NOT NULL,
        FOREIGN KEY (asamblea_id) REFERENCES asambleas(id),
        FOREIGN KEY (cedula_da_poder) REFERENCES residentes(cedula),
        FOREIGN KEY (cedula_recibe_poder) REFERENCES residentes(cedula),
        UNIQUE (asamblea_id, cedula_da_poder)
    )
    ''')

    # Tabla de preguntas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS preguntas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asamblea_id INTEGER NOT NULL,
        texto_pregunta TEXT NOT NULL,
        opciones_configuradas TEXT, -- Comma-separated e.g., "Sí,No,Abstenerse"
        activa INTEGER DEFAULT 0,
        FOREIGN KEY (asamblea_id) REFERENCES asambleas(id)
    )
    ''')

    # Tabla de votos
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS votos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pregunta_id INTEGER NOT NULL,
        cedula_votante TEXT NOT NULL,
        opcion_elegida TEXT NOT NULL, -- Texto de la opción elegida
        FOREIGN KEY (pregunta_id) REFERENCES preguntas(id),
        FOREIGN KEY (cedula_votante) REFERENCES residentes(cedula),
        UNIQUE (pregunta_id, cedula_votante)
    )
    ''')
    conn.commit()
    conn.close()


# --- Clases de la Aplicación ---
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Gestión de Asambleas de Condominio")
        self.root.geometry("1100x750")  # Aumentar un poco el tamaño por los nuevos campos

        style = ttk.Style()
        style.theme_use('clam')

        self.current_assembly_id = None
        self.current_question_id = None
        self.current_question_options = []  # Opciones para la pregunta activa

        self.notebook = ttk.Notebook(root)

        self.resident_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.resident_tab, text='Residentes')
        self.setup_resident_tab()

        self.assembly_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.assembly_tab, text='Asambleas')
        self.setup_assembly_tab()

        self.voting_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.voting_tab, text='Votación en Vivo')
        self.setup_voting_tab()

        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)

        init_db()
        self.load_residents()
        self.load_assemblies()

    def execute_query(self, query, params=(), fetchone=False, fetchall=False, commit=False):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            if commit:
                conn.commit()
            result = None
            if fetchone:
                result = cursor.fetchone()
            if fetchall:
                result = cursor.fetchall()
        except sqlite3.Error as e:
            messagebox.showerror("Error de Base de Datos", f"Error: {e}\nQuery: {query}\nParams: {params}")
            # Podrías querer registrar el error en un log también
            if conn:  # Asegurar que la conexión no se cierre si ya está cerrada
                conn.rollback()  # Revertir cambios si la transacción falló
            return None  # O re-lanzar la excepción dependiendo de cómo quieras manejarlo
        finally:
            if conn:
                conn.close()
        return result

    # --- Pestaña de Residentes ---
    def setup_resident_tab(self):
        frame = self.resident_tab

        form_frame = ttk.LabelFrame(frame, text="Registrar/Actualizar Residente", padding=10)
        form_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(form_frame, text="Cédula:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.resident_cedula_entry = ttk.Entry(form_frame, width=40)
        self.resident_cedula_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(form_frame, text="Nombre:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.resident_name_entry = ttk.Entry(form_frame, width=40)
        self.resident_name_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(form_frame, text="Celular:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.resident_phone_entry = ttk.Entry(form_frame, width=40)
        self.resident_phone_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(form_frame, text="Casa/Apto:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.resident_house_entry = ttk.Entry(form_frame, width=40)
        self.resident_house_entry.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        self.resident_cedula_to_update = None  # Usaremos esto para saber si estamos actualizando

        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="Guardar Residente", command=self.save_resident).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Limpiar Campos", command=self.clear_resident_fields).pack(side=tk.LEFT, padx=5)

        list_frame = ttk.LabelFrame(frame, text="Lista de Residentes Activos", padding=10)
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)

        columns = ("cedula", "nombre", "celular", "casa")  # 'activo' ya no se muestra directamente
        self.resident_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        for col in columns:
            self.resident_tree.heading(col, text=col.capitalize())
            self.resident_tree.column(col, width=120 if col != "nombre" else 250, anchor=tk.W)

        self.resident_tree.pack(fill="both", expand=True, side=tk.LEFT)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.resident_tree.yview)
        self.resident_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill="y")

        self.resident_tree.bind("<<TreeviewSelect>>", self.on_resident_select)

        resident_actions_frame = ttk.Frame(list_frame)
        resident_actions_frame.pack(pady=5, fill="x")
        ttk.Button(resident_actions_frame, text="Marcar Seleccionado como Inactivo",
                   command=self.deactivate_resident).pack(side=tk.LEFT, padx=5)
        ttk.Button(resident_actions_frame, text="Refrescar Lista", command=self.load_residents).pack(side=tk.LEFT,
                                                                                                     padx=5)

    def clear_resident_fields(self):
        self.resident_cedula_entry.config(state='normal')  # Habilitar si estaba deshabilitado para update
        self.resident_cedula_entry.delete(0, tk.END)
        self.resident_name_entry.delete(0, tk.END)
        self.resident_phone_entry.delete(0, tk.END)
        self.resident_house_entry.delete(0, tk.END)
        self.resident_cedula_to_update = None
        self.resident_cedula_entry.focus()

    def save_resident(self):
        cedula = self.resident_cedula_entry.get().strip()
        nombre = self.resident_name_entry.get().strip()
        celular = self.resident_phone_entry.get().strip()
        casa = self.resident_house_entry.get().strip()

        if not cedula or not nombre or not celular or not casa:
            messagebox.showerror("Error", "Cédula, nombre, celular y casa/apto son obligatorios.")
            return

        try:
            if self.resident_cedula_to_update:  # Actualizando un residente existente
                self.execute_query("UPDATE residentes SET nombre=?, celular=?, casa=? WHERE cedula=?",
                                   (nombre, celular, casa, self.resident_cedula_to_update), commit=True)
                messagebox.showinfo("Éxito", "Residente actualizado correctamente.")
            else:  # Creando un nuevo residente
                self.execute_query(
                    "INSERT INTO residentes (cedula, nombre, celular, casa, activo) VALUES (?, ?, ?, ?, 1)",
                    (cedula, nombre, celular, casa), commit=True)
                messagebox.showinfo("Éxito", "Residente registrado correctamente.")

            self.clear_resident_fields()
            self.load_residents()
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: residentes.cedula" in str(e):
                messagebox.showerror("Error de Duplicado", f"La cédula '{cedula}' ya está registrada.")
            elif "UNIQUE constraint failed: residentes.celular" in str(e):
                messagebox.showerror("Error de Duplicado", f"El celular '{celular}' ya está registrado.")
            else:
                messagebox.showerror("Error de Integridad", f"Error al guardar: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error inesperado: {e}")

    def on_resident_select(self, event=None):
        selected_item = self.resident_tree.focus()
        if not selected_item:
            return

        values = self.resident_tree.item(selected_item, "values")
        if values:
            self.resident_cedula_to_update = values[0]  # Cédula está en la primera columna
            self.resident_cedula_entry.delete(0, tk.END)
            self.resident_cedula_entry.insert(0, values[0])
            self.resident_cedula_entry.config(state='disabled')  # No permitir cambiar cédula al actualizar

            self.resident_name_entry.delete(0, tk.END)
            self.resident_name_entry.insert(0, values[1])
            self.resident_phone_entry.delete(0, tk.END)
            self.resident_phone_entry.insert(0, values[2])
            self.resident_house_entry.delete(0, tk.END)
            self.resident_house_entry.insert(0, values[3])

    def load_residents(self):
        for i in self.resident_tree.get_children():
            self.resident_tree.delete(i)

        rows = self.execute_query(
            "SELECT cedula, nombre, celular, casa FROM residentes WHERE activo = 1 ORDER BY nombre", fetchall=True)
        if rows is not None:
            for row in rows:
                self.resident_tree.insert("", "end", values=row)
        self.update_resident_comboboxes()

    def update_resident_comboboxes(self):
        residents_data = self.execute_query(
            "SELECT cedula, nombre, casa FROM residentes WHERE activo = 1 ORDER BY nombre", fetchall=True)
        resident_list = []
        if residents_data:
            resident_list = [f"{r[0]}: {r[1]} ({r[2]})" for r in residents_data]  # Cédula: Nombre (Casa)

        if hasattr(self, 'proxy_giver_combobox'):
            self.proxy_giver_combobox['values'] = resident_list
            self.proxy_giver_combobox.set('')
        if hasattr(self, 'proxy_receiver_combobox'):
            self.proxy_receiver_combobox['values'] = resident_list
            self.proxy_receiver_combobox.set('')
        # voting_resident_combobox se actualiza con load_eligible_voters

    def deactivate_resident(self):
        selected_item = self.resident_tree.focus()
        if not selected_item:
            messagebox.showwarning("Advertencia", "Seleccione un residente para marcar como inactivo.")
            return

        cedula_residente = self.resident_tree.item(selected_item, "values")[0]
        nombre_residente = self.resident_tree.item(selected_item, "values")[1]

        if messagebox.askyesno("Confirmar Inactivación",
                               f"¿Está seguro de que desea marcar a '{nombre_residente}' (Cédula: {cedula_residente}) como inactivo?"):
            try:
                self.execute_query("UPDATE residentes SET activo = 0 WHERE cedula=?", (cedula_residente,), commit=True)
                messagebox.showinfo("Éxito", f"Residente '{nombre_residente}' marcado como inactivo.")
                self.load_residents()
                self.clear_resident_fields()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo actualizar el estado del residente. Error: {e}")

    # --- Pestaña de Asambleas ---
    def setup_assembly_tab(self):
        frame = self.assembly_tab

        assembly_selection_frame = ttk.LabelFrame(frame, text="Gestión de Asamblea", padding=10)
        assembly_selection_frame.pack(padx=10, pady=10, fill="x")
        # ... (código para fecha y descripción de asamblea sin cambios) ...
        ttk.Label(assembly_selection_frame, text="Fecha (YYYY-MM-DD):").grid(row=0, column=0, padx=5, pady=5,
                                                                             sticky="w")
        self.assembly_date_entry = ttk.Entry(assembly_selection_frame, width=30)
        self.assembly_date_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(assembly_selection_frame, text="Descripción:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.assembly_desc_entry = ttk.Entry(assembly_selection_frame, width=30)
        self.assembly_desc_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(assembly_selection_frame, text="Crear Nueva Asamblea", command=self.create_assembly).grid(row=2,
                                                                                                             column=0,
                                                                                                             columnspan=2,
                                                                                                             pady=10)

        assembly_list_frame = ttk.LabelFrame(frame, text="Asambleas Existentes", padding=10)
        assembly_list_frame.pack(padx=10, pady=10, fill="x")
        self.assembly_combobox = ttk.Combobox(assembly_list_frame, state="readonly", width=65)  # Un poco más ancho
        self.assembly_combobox.pack(side=tk.LEFT, padx=5)
        self.assembly_combobox.bind("<<ComboboxSelected>>", self.on_assembly_selected)

        powers_frame = ttk.LabelFrame(frame, text="Gestión de Poderes (para la asamblea seleccionada)", padding=10)
        powers_frame.pack(padx=10, pady=10, fill="x")
        # ... (comboboxes de poderes y treeview sin cambios estructurales, solo usan cédula) ...
        ttk.Label(powers_frame, text="Residente que da poder:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.proxy_giver_combobox = ttk.Combobox(powers_frame, state="readonly", width=40)
        self.proxy_giver_combobox.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(powers_frame, text="Residente que recibe poder:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.proxy_receiver_combobox = ttk.Combobox(powers_frame, state="readonly", width=40)
        self.proxy_receiver_combobox.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(powers_frame, text="Asignar Poder", command=self.assign_proxy).grid(row=2, column=0, columnspan=2,
                                                                                       pady=10)

        self.powers_tree = ttk.Treeview(powers_frame, columns=("id_poder", "da_poder_cedula", "recibe_poder_cedula"),
                                        show="headings", height=4)
        self.powers_tree.heading("id_poder", text="ID")
        self.powers_tree.heading("da_poder_cedula", text="Da Poder (Cédula - Nombre)")
        self.powers_tree.heading("recibe_poder_cedula", text="Recibe Poder (Cédula - Nombre)")
        self.powers_tree.column("id_poder", width=30, anchor=tk.W)
        self.powers_tree.column("da_poder_cedula", width=250, anchor=tk.W)
        self.powers_tree.column("recibe_poder_cedula", width=250, anchor=tk.W)
        self.powers_tree.grid(row=3, column=0, columnspan=2, pady=5, sticky="ew")
        ttk.Button(powers_frame, text="Eliminar Poder Seleccionado", command=self.delete_proxy).grid(row=4, column=0,
                                                                                                     columnspan=2,
                                                                                                     pady=5)

        questions_frame = ttk.LabelFrame(frame, text="Preguntas de la Asamblea", padding=10)
        questions_frame.pack(padx=10, pady=10, fill="both", expand=True)

        ttk.Label(questions_frame, text="Texto de la Pregunta:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.question_text_entry = ttk.Entry(questions_frame, width=50)
        self.question_text_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(questions_frame, text="Opciones (separadas por coma):").grid(row=1, column=0, padx=5, pady=5,
                                                                               sticky="w")
        self.question_options_entry = ttk.Entry(questions_frame, width=50)
        self.question_options_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.question_options_entry.insert(0, "Acepta,No Acepta,En Blanco")  # Opciones por defecto

        ttk.Button(questions_frame, text="Agregar Pregunta", command=self.add_question_to_assembly).grid(row=1,
                                                                                                         column=2,
                                                                                                         padx=5, pady=5)

        self.questions_tree = ttk.Treeview(questions_frame, columns=("id_q", "pregunta_t", "opciones_q", "estado_q"),
                                           show="headings", height=5)
        self.questions_tree.heading("id_q", text="ID")
        self.questions_tree.heading("pregunta_t", text="Pregunta")
        self.questions_tree.heading("opciones_q", text="Opciones")
        self.questions_tree.heading("estado_q", text="Estado")
        self.questions_tree.column("id_q", width=30, anchor=tk.W)
        self.questions_tree.column("pregunta_t", width=300, anchor=tk.W)
        self.questions_tree.column("opciones_q", width=200, anchor=tk.W)
        self.questions_tree.column("estado_q", width=100, anchor=tk.W)
        self.questions_tree.grid(row=2, column=0, columnspan=3, pady=5, sticky="nsew")

        questions_frame.grid_columnconfigure(1, weight=1)
        questions_frame.grid_rowconfigure(2, weight=1)

    def create_assembly(self):  # Sin cambios, solo la llamada a load_assemblies
        fecha = self.assembly_date_entry.get()
        descripcion = self.assembly_desc_entry.get()
        if not fecha or not descripcion:
            messagebox.showerror("Error", "Fecha y descripción son obligatorias para crear una asamblea.")
            return
        try:
            self.execute_query("INSERT INTO asambleas (fecha, descripcion) VALUES (?, ?)", (fecha, descripcion),
                               commit=True)
            messagebox.showinfo("Éxito", "Asamblea creada.")
            self.load_assemblies()
            self.assembly_date_entry.delete(0, tk.END)
            self.assembly_desc_entry.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear la asamblea: {e}")

    def load_assemblies(self):  # Sin cambios, solo la llamada a on_assembly_selected
        assemblies = self.execute_query("SELECT id, fecha, descripcion FROM asambleas ORDER BY fecha DESC, id DESC",
                                        fetchall=True)
        if assemblies is not None:
            self.assembly_combobox['values'] = [f"{row[0]}: {row[1]} - {row[2]}" for row in assemblies]
            if assemblies:
                self.assembly_combobox.current(0)
                self.on_assembly_selected()
            else:
                self.assembly_combobox.set('')
                self.current_assembly_id = None
                self.clear_assembly_details()
        else:  # Falló la consulta
            self.assembly_combobox['values'] = []
            self.assembly_combobox.set('')
            self.current_assembly_id = None
            self.clear_assembly_details()

    def on_assembly_selected(self, event=None):  # Sin cambios, solo la llamada a load_selected_assembly_details
        selection = self.assembly_combobox.get()
        if selection:
            try:
                self.current_assembly_id = int(selection.split(":")[0])
                self.load_selected_assembly_details()
            except ValueError:
                messagebox.showerror("Error", "Formato de selección de asamblea inválido.")
                self.current_assembly_id = None
                self.clear_assembly_details()
        else:
            self.current_assembly_id = None
            self.clear_assembly_details()

    def load_selected_assembly_details(self):  # Sin cambios, solo las llamadas a las sub-funciones de carga
        if not self.current_assembly_id:
            self.clear_assembly_details()
            return
        self.update_resident_comboboxes()
        self.load_proxies_for_assembly()
        self.load_questions_for_assembly()
        self.load_questions_for_voting_tab()

    def clear_assembly_details(self):  # Actualizado para limpiar nuevos campos/estados
        if hasattr(self, 'proxy_giver_combobox'): self.proxy_giver_combobox.set('')
        if hasattr(self, 'proxy_receiver_combobox'): self.proxy_receiver_combobox.set('')
        if hasattr(self, 'powers_tree'):
            for i in self.powers_tree.get_children(): self.powers_tree.delete(i)
        if hasattr(self, 'question_text_entry'): self.question_text_entry.delete(0, tk.END)
        if hasattr(self, 'question_options_entry'):
            self.question_options_entry.delete(0, tk.END)
            self.question_options_entry.insert(0, "Acepta,No Acepta,En Blanco")  # Reset a default
        if hasattr(self, 'questions_tree'):
            for i in self.questions_tree.get_children(): self.questions_tree.delete(i)

        self.current_question_id = None
        self.current_question_options = []
        if hasattr(self, 'active_question_label'): self.active_question_label.config(text="Pregunta Activa: Ninguna")
        if hasattr(self, 'voting_resident_combobox'):
            self.voting_resident_combobox.set('')
            self.voting_resident_combobox['values'] = []
        if hasattr(self, 'vote_option_var_string'): self.vote_option_var_string.set("")  # Ahora es StringVar

        if hasattr(self, 'options_radio_frame') and self.options_radio_frame:
            for widget in self.options_radio_frame.winfo_children(): widget.destroy()

        if hasattr(self, 'results_canvas_widget') and self.results_canvas_widget:
            self.results_canvas_widget.get_tk_widget().destroy()
            self.results_canvas_widget = None
        if hasattr(self, 'voting_question_combobox'):
            self.voting_question_combobox['values'] = []
            self.voting_question_combobox.set('')

    def assign_proxy(self):
        if not self.current_assembly_id:
            messagebox.showerror("Error", "Seleccione una asamblea primero.")
            return
        giver_selection = self.proxy_giver_combobox.get()
        receiver_selection = self.proxy_receiver_combobox.get()
        if not giver_selection or not receiver_selection:
            messagebox.showerror("Error", "Seleccione ambos residentes para asignar el poder.")
            return
        try:
            cedula_da_poder = giver_selection.split(":")[0].strip()
            cedula_recibe_poder = receiver_selection.split(":")[0].strip()
            if cedula_da_poder == cedula_recibe_poder:
                messagebox.showerror("Error", "Un residente no puede darse poder a sí mismo.")
                return
            self.execute_query(
                "INSERT INTO poderes (asamblea_id, cedula_da_poder, cedula_recibe_poder) VALUES (?, ?, ?)",
                (self.current_assembly_id, cedula_da_poder, cedula_recibe_poder), commit=True)
            messagebox.showinfo("Éxito", "Poder asignado.")
            self.load_proxies_for_assembly()
            if self.current_question_id: self.load_eligible_voters()
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Este residente ya ha otorgado un poder para esta asamblea.")
        except ValueError:
            messagebox.showerror("Error", "Selección de residente inválida (formato cédula: nombre).")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo asignar el poder: {e}")

    def load_proxies_for_assembly(self):
        for i in self.powers_tree.get_children(): self.powers_tree.delete(i)
        if not self.current_assembly_id: return
        query = """
        SELECT p.id, r1.cedula || ': ' || r1.nombre, r2.cedula || ': ' || r2.nombre
        FROM poderes p
        JOIN residentes r1 ON p.cedula_da_poder = r1.cedula
        JOIN residentes r2 ON p.cedula_recibe_poder = r2.cedula
        WHERE p.asamblea_id = ? AND r1.activo = 1 AND r2.activo = 1
        """
        proxies = self.execute_query(query, (self.current_assembly_id,), fetchall=True)
        if proxies:
            for p_data in proxies: self.powers_tree.insert("", "end", values=p_data)

    def delete_proxy(self):
        selected_item = self.powers_tree.focus()
        if not selected_item:
            messagebox.showwarning("Advertencia", "Seleccione un poder para eliminar.")
            return
        if not self.current_assembly_id:
            messagebox.showerror("Error", "No hay una asamblea activa seleccionada.")
            return
        if messagebox.askyesno("Confirmar", "¿Está seguro de que desea eliminar este poder?"):
            power_id = self.powers_tree.item(selected_item, "values")[0]
            try:
                self.execute_query("DELETE FROM poderes WHERE id=? AND asamblea_id=?",
                                   (power_id, self.current_assembly_id), commit=True)
                messagebox.showinfo("Éxito", "Poder eliminado.")
                self.load_proxies_for_assembly()
                if self.current_question_id: self.load_eligible_voters()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar el poder: {e}")

    def add_question_to_assembly(self):
        if not self.current_assembly_id:
            messagebox.showerror("Error", "Seleccione una asamblea primero.")
            return
        q_text = self.question_text_entry.get().strip()
        q_options = self.question_options_entry.get().strip()
        if not q_text:
            messagebox.showerror("Error", "El texto de la pregunta no puede estar vacío.")
            return
        if not q_options:  # Usar opciones por defecto si el campo está vacío
            q_options = "Acepta,No Acepta,En Blanco"

        try:
            self.execute_query(
                "INSERT INTO preguntas (asamblea_id, texto_pregunta, opciones_configuradas, activa) VALUES (?, ?, ?, 0)",
                (self.current_assembly_id, q_text, q_options), commit=True)
            messagebox.showinfo("Éxito", "Pregunta agregada a la asamblea.")
            self.question_text_entry.delete(0, tk.END)
            self.question_options_entry.delete(0, tk.END)
            self.question_options_entry.insert(0, "Acepta,No Acepta,En Blanco")  # Reset a default
            self.load_questions_for_assembly()
            self.load_questions_for_voting_tab()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo agregar la pregunta: {e}")

    def load_questions_for_assembly(self):
        for i in self.questions_tree.get_children(): self.questions_tree.delete(i)
        if not self.current_assembly_id: return

        questions_data = self.execute_query(
            "SELECT id, texto_pregunta, opciones_configuradas, activa FROM preguntas WHERE asamblea_id = ? ORDER BY id",
            (self.current_assembly_id,), fetchall=True)
        if questions_data:
            for q_id, q_text, q_opts, q_active in questions_data:
                estado = "Activa para Votación" if q_active == 1 else "Inactiva"
                self.questions_tree.insert("", "end", values=(q_id, q_text, q_opts, estado))

    # --- Pestaña de Votación ---
    def setup_voting_tab(self):
        frame = self.voting_tab

        question_select_frame = ttk.LabelFrame(frame, text="Seleccionar Pregunta para Votación", padding=10)
        question_select_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(question_select_frame, text="Pregunta:").pack(side=tk.LEFT, padx=5)
        self.voting_question_combobox = ttk.Combobox(question_select_frame, state="readonly", width=70)  # Más ancho
        self.voting_question_combobox.pack(side=tk.LEFT, padx=5)
        self.voting_question_combobox.bind("<<ComboboxSelected>>", self.on_voting_question_selected_for_display)

        button_frame_votacion = ttk.Frame(question_select_frame)  # Frame para botones
        button_frame_votacion.pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame_votacion, text="Activar Pregunta", command=self.activate_question_for_voting).pack(
            side=tk.TOP, pady=2)
        ttk.Button(button_frame_votacion, text="Cerrar Votación", command=self.close_current_question_voting).pack(
            side=tk.TOP, pady=2)

        self.active_question_label = ttk.Label(frame, text="Pregunta Activa: Ninguna", font=("Arial", 12, "bold"))
        self.active_question_label.pack(pady=10)

        vote_entry_frame = ttk.LabelFrame(frame, text="Registrar Voto (Entrada Manual)", padding=10)
        vote_entry_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(vote_entry_frame, text="Residente Votante:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.voting_resident_combobox = ttk.Combobox(vote_entry_frame, state="readonly", width=40)
        self.voting_resident_combobox.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(vote_entry_frame, text="Opción de Voto:").grid(row=1, column=0, padx=5, pady=5,
                                                                 sticky="nw")  # sticky nw

        # Frame para los radiobuttons dinámicos
        self.options_radio_frame = ttk.Frame(vote_entry_frame)
        self.options_radio_frame.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.vote_option_var_string = tk.StringVar()  # Usar StringVar para texto de opción

        ttk.Button(vote_entry_frame, text="Registrar Voto", command=self.register_vote).grid(row=2, column=0,
                                                                                             columnspan=2, pady=10)
        vote_entry_frame.grid_columnconfigure(1, weight=1)

        results_frame = ttk.LabelFrame(frame, text="Resultados de la Pregunta", padding=10)
        results_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.results_display_frame = results_frame
        self.results_canvas_widget = None

    def load_questions_for_voting_tab(self):
        if not self.current_assembly_id:
            self.voting_question_combobox['values'] = []
            self.voting_question_combobox.set('')
            self.clear_voting_area()
            return

        questions = self.execute_query(
            "SELECT id, texto_pregunta, opciones_configuradas FROM preguntas WHERE asamblea_id = ? ORDER BY id",
            (self.current_assembly_id,), fetchall=True
        )
        if questions is not None:
            self.voting_question_combobox['values'] = [f"{q[0]}: {q[1]}" for q in questions]
            if questions:
                self.voting_question_combobox.current(0)
                self.on_voting_question_selected_for_display()
            else:
                self.voting_question_combobox.set('')
                self.clear_voting_area()
                ttk.Label(self.results_display_frame, text="No hay preguntas para esta asamblea.").pack(pady=20)
        else:
            self.voting_question_combobox['values'] = []
            self.voting_question_combobox.set('')
            self.clear_voting_area()

    def clear_voting_area(self):
        """Limpia el área de opciones de voto y resultados."""
        self.current_question_id = None
        self.current_question_options = []
        self.active_question_label.config(text="Pregunta Activa: Ninguna")
        self.voting_resident_combobox.set('')
        self.voting_resident_combobox['values'] = []
        self.vote_option_var_string.set("")

        if hasattr(self, 'options_radio_frame'):
            for widget in self.options_radio_frame.winfo_children():
                widget.destroy()

        if hasattr(self, 'results_canvas_widget') and self.results_canvas_widget:
            self.results_canvas_widget.get_tk_widget().destroy()
            self.results_canvas_widget = None
        if hasattr(self, 'results_display_frame'):  # Limpiar también etiquetas de texto
            for widget in self.results_display_frame.winfo_children():
                widget.destroy()

    def on_voting_question_selected_for_display(self, event=None):
        selection = self.voting_question_combobox.get()
        if selection:
            try:
                question_id_to_display = int(selection.split(":")[0])
                # Si la pregunta seleccionada NO es la pregunta activa para votación,
                # solo mostramos sus resultados y no actualizamos los radiobuttons de voto.
                if question_id_to_display != self.current_question_id:
                    self.update_vote_options_ui(question_id_to_display, for_display_only=True)
                self.display_vote_results_for_question(question_id_to_display)

            except ValueError:
                messagebox.showerror("Error", "Formato de selección de pregunta inválido.")

    def update_vote_options_ui(self, question_id, for_display_only=False):
        """Actualiza los radiobuttons de opciones de voto para la pregunta dada."""
        for widget in self.options_radio_frame.winfo_children():
            widget.destroy()

        self.current_question_options = []
        question_data = self.execute_query("SELECT opciones_configuradas FROM preguntas WHERE id = ?", (question_id,),
                                           fetchone=True)

        if question_data and question_data[0]:
            self.current_question_options = [opt.strip() for opt in question_data[0].split(',')]
        else:  # Opciones por defecto si no hay nada configurado o la pregunta no existe
            self.current_question_options = ["Acepta", "No Acepta", "En Blanco"]

        self.vote_option_var_string.set("")  # Deseleccionar opción previa

        if not for_display_only:  # Solo crear radiobuttons si estamos activando para votar
            for option_text in self.current_question_options:
                rb = ttk.Radiobutton(self.options_radio_frame, text=option_text, variable=self.vote_option_var_string,
                                     value=option_text)
                rb.pack(anchor=tk.W, pady=2)
        elif not self.current_question_id:  # Si no hay pregunta activa, mostrar un mensaje
            ttk.Label(self.options_radio_frame, text="Active una pregunta para ver opciones de voto.").pack(anchor=tk.W)

    def activate_question_for_voting(self):
        selection = self.voting_question_combobox.get()
        if not selection:
            messagebox.showerror("Error", "Seleccione una pregunta para activar.")
            return
        if not self.current_assembly_id:
            messagebox.showerror("Error", "Primero debe seleccionar o cargar una asamblea activa.")
            return
        try:
            new_active_question_id = int(selection.split(":")[0])
        except ValueError:
            messagebox.showerror("Error", "Formato de selección de pregunta inválido.")
            return

        if self.current_question_id is not None and self.current_question_id != new_active_question_id:
            self.execute_query("UPDATE preguntas SET activa = 0 WHERE id = ? AND asamblea_id = ?",
                               (self.current_question_id, self.current_assembly_id), commit=True)

        self.execute_query("UPDATE preguntas SET activa = 1 WHERE id = ? AND asamblea_id = ?",
                           (new_active_question_id, self.current_assembly_id), commit=True)

        self.current_question_id = new_active_question_id
        question_text = selection.split(":", 1)[1].strip()
        self.active_question_label.config(text=f"Pregunta Activa (ID: {self.current_question_id}): {question_text}")

        self.update_vote_options_ui(self.current_question_id)  # Actualizar radiobuttons
        self.load_eligible_voters()
        self.display_vote_results_for_question(self.current_question_id)
        self.load_questions_for_assembly()
        messagebox.showinfo("Votación Activada", f"La pregunta '{question_text}' está activa para votación.")

    def close_current_question_voting(self):
        if not self.current_question_id:
            messagebox.showwarning("Advertencia", "Ninguna pregunta está activa para votación.")
            return

        question_id_to_close = self.current_question_id
        q_info = self.execute_query("SELECT texto_pregunta FROM preguntas WHERE id = ?", (question_id_to_close,),
                                    fetchone=True)
        question_text_closed = q_info[0] if q_info else f"ID {question_id_to_close}"

        self.execute_query("UPDATE preguntas SET activa = 0 WHERE id = ?", (question_id_to_close,), commit=True)
        self.load_questions_for_assembly()

        messagebox.showinfo("Votación Cerrada",
                            f"Se ha cerrado la votación para la pregunta: '{question_text_closed}'.")
        self.display_vote_results_for_question(question_id_to_close, final=True)

        self.current_question_id = None
        self.current_question_options = []
        self.active_question_label.config(text="Pregunta Activa: Ninguna")
        self.voting_resident_combobox.set('')
        self.voting_resident_combobox['values'] = []
        self.vote_option_var_string.set("")
        for widget in self.options_radio_frame.winfo_children(): widget.destroy()  # Limpiar radiobuttons

    def load_eligible_voters(self):
        if not self.current_assembly_id:
            self.voting_resident_combobox['values'] = []
            self.voting_resident_combobox.set('')
            return
        query = """
        SELECT r.cedula, r.nombre, r.casa 
        FROM residentes r
        WHERE r.activo = 1 AND r.cedula NOT IN (
            SELECT p.cedula_da_poder 
            FROM poderes p 
            WHERE p.asamblea_id = ?
        )
        ORDER BY r.nombre
        """
        eligible_voters_data = self.execute_query(query, (self.current_assembly_id,), fetchall=True)
        eligible_voters_list = []
        if eligible_voters_data:
            eligible_voters_list = [f"{r_cedula}: {r_nombre} ({r_casa})" for r_cedula, r_nombre, r_casa in
                                    eligible_voters_data]

        self.voting_resident_combobox['values'] = eligible_voters_list
        if eligible_voters_list:
            self.voting_resident_combobox.current(0)
        else:
            self.voting_resident_combobox.set('')

    def register_vote(self):
        if not self.current_question_id:
            messagebox.showerror("Error", "Ninguna pregunta está activa para votación.")
            return
        voter_selection = self.voting_resident_combobox.get()
        opcion_elegida_str = self.vote_option_var_string.get()  # Obtener el texto de la opción

        if not voter_selection:
            messagebox.showerror("Error", "Seleccione el residente que está votando.")
            return
        if not opcion_elegida_str:  # Verificar que se haya seleccionado una opción
            messagebox.showerror("Error", "Seleccione una opción de voto.")
            return
        try:
            cedula_votante = voter_selection.split(":")[0].strip()

            existing_vote = self.execute_query(
                "SELECT id FROM votos WHERE pregunta_id = ? AND cedula_votante = ?",
                (self.current_question_id, cedula_votante), fetchone=True
            )
            if existing_vote:
                if messagebox.askyesno("Confirmar Cambio de Voto",
                                       "Este residente ya ha votado. ¿Desea cambiar el voto?"):
                    self.execute_query(
                        "UPDATE votos SET opcion_elegida = ? WHERE pregunta_id = ? AND cedula_votante = ?",
                        (opcion_elegida_str, self.current_question_id, cedula_votante), commit=True
                    )
                    messagebox.showinfo("Éxito", "Voto actualizado.")
                else:
                    return
            else:
                self.execute_query("INSERT INTO votos (pregunta_id, cedula_votante, opcion_elegida) VALUES (?, ?, ?)",
                                   (self.current_question_id, cedula_votante, opcion_elegida_str), commit=True)
                messagebox.showinfo("Éxito", "Voto registrado.")

            self.display_vote_results_for_question(self.current_question_id)
            self.vote_option_var_string.set("")  # Resetear opción de voto
        except ValueError:
            messagebox.showerror("Error", "Selección de residente inválida.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar el voto: {e}")

    def get_voting_weights(self):
        if not self.current_assembly_id: return {}
        weights = {}
        residents_can_vote = self.execute_query(
            """SELECT r.cedula FROM residentes r
               WHERE r.activo = 1 AND r.cedula NOT IN (
                   SELECT p.cedula_da_poder FROM poderes p WHERE p.asamblea_id = ?
               )""",
            (self.current_assembly_id,), fetchall=True
        )
        if residents_can_vote:
            for r_tuple in residents_can_vote: weights[r_tuple[0]] = 1

        proxies_received = self.execute_query(
            """SELECT cedula_recibe_poder, COUNT(cedula_da_poder) 
               FROM poderes 
               WHERE asamblea_id = ? 
               GROUP BY cedula_recibe_poder""",
            (self.current_assembly_id,), fetchall=True
        )
        if proxies_received:
            for receiver_cedula, count in proxies_received:
                if receiver_cedula in weights: weights[receiver_cedula] += count
        return weights

    def display_vote_results_for_question(self, question_id_for_results, final=False):
        if not self.current_assembly_id:
            messagebox.showwarning("Advertencia", "No hay una asamblea seleccionada.")
            self.clear_voting_area()  # Limpiar área de resultados si no hay asamblea
            return
        if not question_id_for_results:
            self.clear_voting_area()
            ttk.Label(self.results_display_frame, text="Seleccione una pregunta para ver sus resultados.").pack(pady=20)
            return

        if hasattr(self, 'results_canvas_widget') and self.results_canvas_widget:
            self.results_canvas_widget.get_tk_widget().destroy()
        for widget in self.results_display_frame.winfo_children(): widget.destroy()
        self.results_canvas_widget = None

        votes_data = self.execute_query(
            "SELECT cedula_votante, opcion_elegida FROM votos WHERE pregunta_id = ?",
            (question_id_for_results,), fetchall=True
        )
        q_info = self.execute_query("SELECT texto_pregunta, activa, opciones_configuradas FROM preguntas WHERE id = ?",
                                    (question_id_for_results,), fetchone=True)
        if not q_info:
            ttk.Label(self.results_display_frame,
                      text=f"No se encontró información para la pregunta ID {question_id_for_results}.").pack(pady=20)
            return

        q_text, q_is_active_in_db, q_options_str = q_info
        q_options_list = [opt.strip() for opt in q_options_str.split(',')] if q_options_str else ["Acepta", "No Acepta",
                                                                                                  "En Blanco"]

        if not votes_data:
            ttk.Label(self.results_display_frame, text=f"Aún no hay votos registrados para:\n'{q_text}'").pack(pady=20)
            return

        voting_weights_for_assembly = self.get_voting_weights()
        weighted_results = Counter()

        for cedula_votante, opcion_elegida_text in votes_data:
            weight_of_this_voter_event = voting_weights_for_assembly.get(cedula_votante, 0)
            weighted_results[opcion_elegida_text] += weight_of_this_voter_event

        total_weighted_votes_cast = sum(weighted_results.values())

        chart_labels = []
        chart_sizes = []
        raw_counts_display = Counter()

        # Asegurar que todas las opciones configuradas aparezcan, incluso si no tienen votos
        for option_text_label in q_options_list:
            total_weight_for_option = weighted_results[option_text_label]  # Será 0 si no hay votos

            count_for_option = sum(1 for _, o_elegida in votes_data if o_elegida == option_text_label)
            raw_counts_display[option_text_label] = count_for_option

            if total_weighted_votes_cast > 0:
                percentage = (total_weight_for_option / total_weighted_votes_cast) * 100
                chart_labels.append(f"{option_text_label}\n({total_weight_for_option} pesos, {percentage:.1f}%)")
            else:
                chart_labels.append(f"{option_text_label}\n({total_weight_for_option} pesos)")
            chart_sizes.append(total_weight_for_option)

        if not chart_sizes or all(s == 0 for s in chart_sizes):
            ttk.Label(self.results_display_frame,
                      text=f"No hay votos con peso válidos para graficar para:\n'{q_text}'").pack(pady=20)
            return

        fig, ax = plt.subplots(figsize=(6, 4.5))  # Un poco más alto para la leyenda

        wedges, texts, autotexts = ax.pie(
            chart_sizes, labels=None,
            autopct=lambda p: '{:.1f}%'.format(p) if p > 0 and total_weighted_votes_cast > 0 else '',
            startangle=90, pctdistance=0.85, wedgeprops=dict(width=0.4)
        )
        ax.axis('equal')
        ax.legend(wedges, chart_labels, title="Opciones", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1),
                  fontsize='small')
        plt.subplots_adjust(left=0.05, right=0.65, top=0.9, bottom=0.05)  # Ajustar márgenes

        title_text = f"Resultados: {q_text}"
        if final:
            title_text = f"Resultados Finales: {q_text}"
        elif self.current_question_id == question_id_for_results and q_is_active_in_db:
            title_text = f"Resultados Parciales: {q_text} (Votación Abierta)"
        elif not q_is_active_in_db:
            title_text = f"Resultados (Votación Cerrada): {q_text}"
        plt.title(title_text, pad=20, loc='center', fontsize=10)

        info_text_lines = [f"Pregunta ID: {question_id_for_results}"]
        info_text_lines.append("\nConteo de votos (número de votantes):")
        for opt_text, count in raw_counts_display.items():
            info_text_lines.append(f"- {opt_text}: {count} votante{'s' if count != 1 else ''}")
        info_text_lines.append(f"\nTotal de peso de votos emitidos: {total_weighted_votes_cast}")
        total_possible_weight_in_assembly = sum(voting_weights_for_assembly.values())
        info_text_lines.append(f"Total de peso posible en la asamblea: {total_possible_weight_in_assembly}")
        if total_possible_weight_in_assembly > 0:
            participation = (total_weighted_votes_cast / total_possible_weight_in_assembly) * 100
            info_text_lines.append(f"Participación (peso emitido vs. posible): {participation:.1f}%")

        ttk.Label(self.results_display_frame, text="\n".join(info_text_lines), justify=tk.LEFT, wraplength=380).pack(
            pady=5, anchor='w', padx=5)

        canvas = FigureCanvasTkAgg(fig, master=self.results_display_frame)
        canvas.draw()
        self.results_canvas_widget = canvas.get_tk_widget()
        self.results_canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        plt.close(fig)


# --- Main ---
if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()

