import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import Counter
import os

# --- Configuración de la Base de Datos ---
# La aplicación Python se ejecuta en el HOST.
# La base de datos SQLite (un archivo) residirá en un directorio en el HOST,
# el cual será montado como un volumen por un contenedor Docker.
HOST_DATA_DIR = "condominio_db_data"  # Directorio en el host donde vivirá el .db
DB_NAME = os.path.join(HOST_DATA_DIR, 'condominio.db')


# --- Funciones de Base de Datos ---
def init_db():
    """Inicializa la base de datos y crea las tablas si no existen en el HOST_DATA_DIR."""
    # Asegurarse de que el directorio de datos del HOST exista
    if not os.path.exists(HOST_DATA_DIR):
        try:
            os.makedirs(HOST_DATA_DIR)  # Esto crea el directorio en el host
            print(f"Directorio de datos del host creado en: {HOST_DATA_DIR}")
        except OSError as e:
            print(f"Error al crear el directorio de datos del host {HOST_DATA_DIR}: {e}")
            # Es crucial que este directorio sea escribible por el usuario que ejecuta la app.
            raise  # Re-lanzar la excepción para detener la ejecución si el dir no se puede crear

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Tabla de residentes
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS residentes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    # Tabla de poderes (quién da poder a quién para una asamblea específica)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS poderes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asamblea_id INTEGER NOT NULL,
        residente_da_poder_id INTEGER NOT NULL, -- Residente que otorga el poder
        residente_recibe_poder_id INTEGER NOT NULL, -- Residente que ejercerá el voto
        FOREIGN KEY (asamblea_id) REFERENCES asambleas(id),
        FOREIGN KEY (residente_da_poder_id) REFERENCES residentes(id),
        FOREIGN KEY (residente_recibe_poder_id) REFERENCES residentes(id),
        UNIQUE (asamblea_id, residente_da_poder_id) -- Un residente solo puede dar un poder por asamblea
    )
    ''')

    # Tabla de preguntas para una asamblea
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS preguntas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asamblea_id INTEGER NOT NULL,
        texto_pregunta TEXT NOT NULL,
        activa INTEGER DEFAULT 0, -- 0 para inactiva, 1 para activa. Por defecto inactiva al crear.
        FOREIGN KEY (asamblea_id) REFERENCES asambleas(id)
    )
    ''')

    # Tabla de votos
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS votos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pregunta_id INTEGER NOT NULL,
        residente_votante_id INTEGER NOT NULL, -- El ID del residente que físicamente vota (puede ser él mismo o en representación)
        opcion_voto INTEGER NOT NULL, -- 1: Acepta, 2: No Acepta, 3: Voto en Blanco
        FOREIGN KEY (pregunta_id) REFERENCES preguntas(id),
        FOREIGN KEY (residente_votante_id) REFERENCES residentes(id),
        UNIQUE (pregunta_id, residente_votante_id) -- Un residente solo puede votar una vez por pregunta
    )
    ''')
    conn.commit()
    conn.close()


# --- Clases de la Aplicación ---

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Gestión de Asambleas de Condominio")
        self.root.geometry("1000x700")

        # Estilo
        style = ttk.Style()
        style.theme_use('clam')

        # Variables de estado
        self.current_assembly_id = None
        self.current_question_id = None  # ID de la pregunta actualmente activa para votación

        # Crear Notebook (pestañas)
        self.notebook = ttk.Notebook(root)

        # Pestaña de Residentes
        self.resident_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.resident_tab, text='Residentes')
        self.setup_resident_tab()

        # Pestaña de Asambleas
        self.assembly_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.assembly_tab, text='Asambleas')
        self.setup_assembly_tab()

        # Pestaña de Votación
        self.voting_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.voting_tab, text='Votación en Vivo')
        self.setup_voting_tab()

        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)

        # Inicializar DB
        init_db()
        self.load_residents()
        self.load_assemblies()

    def execute_query(self, query, params=(), fetchone=False, fetchall=False, commit=False):
        """Ejecuta una consulta SQL de forma segura."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(query, params)
        if commit:
            conn.commit()
        result = None
        if fetchone:
            result = cursor.fetchone()
        if fetchall:
            result = cursor.fetchall()
        conn.close()
        return result

    # --- Pestaña de Residentes ---
    def setup_resident_tab(self):
        frame = self.resident_tab

        form_frame = ttk.LabelFrame(frame, text="Registrar/Actualizar Residente", padding=10)
        form_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(form_frame, text="Nombre:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.resident_name_entry = ttk.Entry(form_frame, width=40)
        self.resident_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(form_frame, text="Celular:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.resident_phone_entry = ttk.Entry(form_frame, width=40)
        self.resident_phone_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(form_frame, text="Casa/Apto:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.resident_house_entry = ttk.Entry(form_frame, width=40)
        self.resident_house_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        self.resident_id_to_update = None

        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="Guardar Residente", command=self.save_resident).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Limpiar Campos", command=self.clear_resident_fields).pack(side=tk.LEFT, padx=5)

        list_frame = ttk.LabelFrame(frame, text="Lista de Residentes", padding=10)
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)

        columns = ("id", "nombre", "celular", "casa", "activo")
        self.resident_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        for col in columns:
            self.resident_tree.heading(col, text=col.capitalize())
            self.resident_tree.column(col, width=100 if col != "nombre" else 200, anchor=tk.W)

        self.resident_tree.pack(fill="both", expand=True, side=tk.LEFT)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.resident_tree.yview)
        self.resident_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill="y")

        self.resident_tree.bind("<<TreeviewSelect>>", self.on_resident_select)

        resident_actions_frame = ttk.Frame(list_frame)
        resident_actions_frame.pack(pady=5, fill="x")
        ttk.Button(resident_actions_frame, text="Eliminar Seleccionado", command=self.delete_resident).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(resident_actions_frame, text="Refrescar Lista", command=self.load_residents).pack(side=tk.LEFT,
                                                                                                     padx=5)

    def clear_resident_fields(self):
        self.resident_name_entry.delete(0, tk.END)
        self.resident_phone_entry.delete(0, tk.END)
        self.resident_house_entry.delete(0, tk.END)
        self.resident_id_to_update = None
        self.resident_name_entry.focus()

    def save_resident(self):
        nombre = self.resident_name_entry.get().strip()
        celular = self.resident_phone_entry.get().strip()
        casa = self.resident_house_entry.get().strip()

        if not nombre or not celular or not casa:
            messagebox.showerror("Error", "Todos los campos son obligatorios.")
            return

        try:
            if self.resident_id_to_update:
                self.execute_query("UPDATE residentes SET nombre=?, celular=?, casa=? WHERE id=?",
                                   (nombre, celular, casa, self.resident_id_to_update), commit=True)
                messagebox.showinfo("Éxito", "Residente actualizado correctamente.")
            else:
                self.execute_query("INSERT INTO residentes (nombre, celular, casa) VALUES (?, ?, ?)",
                                   (nombre, celular, casa), commit=True)
                messagebox.showinfo("Éxito", "Residente registrado correctamente.")

            self.clear_resident_fields()
            self.load_residents()
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "El número de celular ya está registrado.")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error: {e}")

    def on_resident_select(self, event=None):
        selected_item = self.resident_tree.focus()
        if not selected_item:
            return

        values = self.resident_tree.item(selected_item, "values")
        if values:
            self.resident_id_to_update = values[0]
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
            "SELECT id, nombre, celular, casa, activo FROM residentes WHERE activo = 1 ORDER BY nombre", fetchall=True)
        for row in rows:
            self.resident_tree.insert("", "end", values=row)
        # Actualizar comboboxes que dependen de la lista de residentes
        self.update_resident_comboboxes()

    def update_resident_comboboxes(self):
        """Actualiza todos los comboboxes que listan residentes."""
        residents = self.execute_query("SELECT id, nombre, casa FROM residentes WHERE activo = 1 ORDER BY nombre",
                                       fetchall=True)
        resident_list = [f"{r[0]}: {r[1]} ({r[2]})" for r in residents]

        if hasattr(self, 'proxy_giver_combobox'):
            self.proxy_giver_combobox['values'] = resident_list
        if hasattr(self, 'proxy_receiver_combobox'):
            self.proxy_receiver_combobox['values'] = resident_list
        if hasattr(self, 'voting_resident_combobox'):
            # Este se actualiza de forma más específica en load_eligible_voters
            pass

    def delete_resident(self):
        selected_item = self.resident_tree.focus()
        if not selected_item:
            messagebox.showwarning("Advertencia", "Seleccione un residente para eliminar.")
            return

        if messagebox.askyesno("Confirmar",
                               "¿Está seguro de que desea eliminar este residente? Esto lo marcará como inactivo y podría afectar registros de poderes y votos si ya participaron."):
            resident_id = self.resident_tree.item(selected_item, "values")[0]
            try:
                # En lugar de eliminar, se marca como inactivo para mantener integridad referencial
                self.execute_query("UPDATE residentes SET activo = 0 WHERE id=?", (resident_id,), commit=True)
                messagebox.showinfo("Éxito", "Residente marcado como inactivo.")
                self.load_residents()
                self.clear_resident_fields()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo actualizar el estado del residente. Error: {e}")

    # --- Pestaña de Asambleas ---
    def setup_assembly_tab(self):
        frame = self.assembly_tab

        assembly_selection_frame = ttk.LabelFrame(frame, text="Gestión de Asamblea", padding=10)
        assembly_selection_frame.pack(padx=10, pady=10, fill="x")

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

        self.assembly_combobox = ttk.Combobox(assembly_list_frame, state="readonly", width=50)
        self.assembly_combobox.pack(side=tk.LEFT, padx=5)
        self.assembly_combobox.bind("<<ComboboxSelected>>", self.on_assembly_selected)
        # El botón "Cargar Asamblea" no es estrictamente necesario si se carga al seleccionar.
        # ttk.Button(assembly_list_frame, text="Cargar Asamblea Seleccionada", command=self.load_selected_assembly_details).pack(side=tk.LEFT, padx=5)

        powers_frame = ttk.LabelFrame(frame, text="Gestión de Poderes (para la asamblea seleccionada)", padding=10)
        powers_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(powers_frame, text="Residente que da poder:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.proxy_giver_combobox = ttk.Combobox(powers_frame, state="readonly", width=30)
        self.proxy_giver_combobox.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(powers_frame, text="Residente que recibe poder:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.proxy_receiver_combobox = ttk.Combobox(powers_frame, state="readonly", width=30)
        self.proxy_receiver_combobox.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(powers_frame, text="Asignar Poder", command=self.assign_proxy).grid(row=2, column=0, columnspan=2,
                                                                                       pady=10)

        self.powers_tree = ttk.Treeview(powers_frame, columns=("id_poder", "da_poder", "recibe_poder"), show="headings",
                                        height=5)
        self.powers_tree.heading("id_poder", text="ID Poder")
        self.powers_tree.heading("da_poder", text="Da Poder (Nombre - Casa)")
        self.powers_tree.heading("recibe_poder", text="Recibe Poder (Nombre - Casa)")
        self.powers_tree.column("id_poder", width=50, anchor=tk.W)
        self.powers_tree.column("da_poder", width=250, anchor=tk.W)
        self.powers_tree.column("recibe_poder", width=250, anchor=tk.W)
        self.powers_tree.grid(row=3, column=0, columnspan=2, pady=5, sticky="ew")
        ttk.Button(powers_frame, text="Eliminar Poder Seleccionado", command=self.delete_proxy).grid(row=4, column=0,
                                                                                                     columnspan=2,
                                                                                                     pady=5)

        questions_frame = ttk.LabelFrame(frame, text="Preguntas de la Asamblea", padding=10)
        questions_frame.pack(padx=10, pady=10, fill="both", expand=True)

        ttk.Label(questions_frame, text="Texto de la Pregunta:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.question_text_entry = ttk.Entry(questions_frame, width=60)
        self.question_text_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(questions_frame, text="Agregar Pregunta", command=self.add_question_to_assembly).grid(row=0,
                                                                                                         column=2,
                                                                                                         padx=5, pady=5)

        self.questions_tree = ttk.Treeview(questions_frame, columns=("id_pregunta", "pregunta", "estado"),
                                           show="headings", height=5)
        self.questions_tree.heading("id_pregunta", text="ID")
        self.questions_tree.heading("pregunta", text="Pregunta")
        self.questions_tree.heading("estado", text="Estado")
        self.questions_tree.column("id_pregunta", width=50, anchor=tk.W)
        self.questions_tree.column("pregunta", width=400, anchor=tk.W)
        self.questions_tree.column("estado", width=100, anchor=tk.W)
        self.questions_tree.grid(row=1, column=0, columnspan=3, pady=5, sticky="nsew")

        questions_frame.grid_columnconfigure(1, weight=1)
        questions_frame.grid_rowconfigure(1, weight=1)

    def create_assembly(self):
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

    def load_assemblies(self):
        assemblies = self.execute_query("SELECT id, fecha, descripcion FROM asambleas ORDER BY fecha DESC, id DESC",
                                        fetchall=True)
        self.assembly_combobox['values'] = [f"{row[0]}: {row[1]} - {row[2]}" for row in assemblies]
        if assemblies:
            self.assembly_combobox.current(0)
            self.on_assembly_selected()
        else:
            self.assembly_combobox.set('')
            self.current_assembly_id = None
            self.clear_assembly_details()

    def on_assembly_selected(self, event=None):
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

    def load_selected_assembly_details(self):
        if not self.current_assembly_id:
            self.clear_assembly_details()
            return

        self.update_resident_comboboxes()  # Asegura que los combos de residentes estén actualizados
        self.load_proxies_for_assembly()
        self.load_questions_for_assembly()
        self.load_questions_for_voting_tab()

    def clear_assembly_details(self):
        """Limpia los detalles relacionados con una asamblea específica en las pestañas."""
        self.proxy_giver_combobox.set('')
        self.proxy_receiver_combobox.set('')
        for i in self.powers_tree.get_children():
            self.powers_tree.delete(i)
        self.question_text_entry.delete(0, tk.END)
        for i in self.questions_tree.get_children():
            self.questions_tree.delete(i)

        # Limpiar también la pestaña de votación
        self.current_question_id = None  # Ya no hay pregunta activa para votación si cambiamos de asamblea
        if hasattr(self, 'active_question_label'):
            self.active_question_label.config(text="Pregunta Activa: Ninguna")
        if hasattr(self, 'voting_resident_combobox'):
            self.voting_resident_combobox.set('')
            self.voting_resident_combobox['values'] = []
        if hasattr(self, 'vote_option_var'):
            self.vote_option_var.set(0)
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
            giver_id = int(giver_selection.split(":")[0])
            receiver_id = int(receiver_selection.split(":")[0])

            if giver_id == receiver_id:
                messagebox.showerror("Error", "Un residente no puede darse poder a sí mismo.")
                return

            self.execute_query(
                "INSERT INTO poderes (asamblea_id, residente_da_poder_id, residente_recibe_poder_id) VALUES (?, ?, ?)",
                (self.current_assembly_id, giver_id, receiver_id), commit=True)
            messagebox.showinfo("Éxito", "Poder asignado.")
            self.load_proxies_for_assembly()
            if self.current_question_id:  # Si hay una pregunta activa, recargar votantes elegibles
                self.load_eligible_voters()
        except sqlite3.IntegrityError:
            messagebox.showerror("Error",
                                 "Este residente ya ha otorgado un poder para esta asamblea, o el receptor ya recibió un poder de este otorgante para esta asamblea.")
        except ValueError:
            messagebox.showerror("Error", "Selección de residente inválida.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo asignar el poder: {e}")

    def load_proxies_for_assembly(self):
        for i in self.powers_tree.get_children():
            self.powers_tree.delete(i)

        if not self.current_assembly_id:
            return

        query = """
        SELECT p.id, r1.nombre || ' (' || r1.casa || ')', r2.nombre || ' (' || r2.casa || ')'
        FROM poderes p
        JOIN residentes r1 ON p.residente_da_poder_id = r1.id
        JOIN residentes r2 ON p.residente_recibe_poder_id = r2.id
        WHERE p.asamblea_id = ? AND r1.activo = 1 AND r2.activo = 1
        """
        proxies = self.execute_query(query, (self.current_assembly_id,), fetchall=True)
        for p_data in proxies:
            self.powers_tree.insert("", "end", values=p_data)

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
                if self.current_question_id:  # Si hay una pregunta activa, recargar votantes elegibles
                    self.load_eligible_voters()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar el poder: {e}")

    def add_question_to_assembly(self):
        if not self.current_assembly_id:
            messagebox.showerror("Error", "Seleccione una asamblea primero.")
            return

        q_text = self.question_text_entry.get().strip()
        if not q_text:
            messagebox.showerror("Error", "El texto de la pregunta no puede estar vacío.")
            return

        try:
            # Las preguntas se agregan como inactivas por defecto. Se activan desde la pestaña de votación.
            self.execute_query("INSERT INTO preguntas (asamblea_id, texto_pregunta, activa) VALUES (?, ?, 0)",
                               (self.current_assembly_id, q_text), commit=True)
            messagebox.showinfo("Éxito", "Pregunta agregada a la asamblea.")
            self.question_text_entry.delete(0, tk.END)
            self.load_questions_for_assembly()
            self.load_questions_for_voting_tab()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo agregar la pregunta: {e}")

    def load_questions_for_assembly(self):
        """Carga las preguntas para la asamblea actual en la pestaña 'Asambleas'."""
        for i in self.questions_tree.get_children():
            self.questions_tree.delete(i)

        if not self.current_assembly_id:
            return

        questions_data = self.execute_query(
            "SELECT id, texto_pregunta, activa FROM preguntas WHERE asamblea_id = ? ORDER BY id",
            (self.current_assembly_id,), fetchall=True)
        for q_id, q_text, q_active_status in questions_data:
            estado = "Activa para Votación" if q_active_status == 1 else "Inactiva"
            self.questions_tree.insert("", "end", values=(q_id, q_text, estado))

    # --- Pestaña de Votación ---
    def setup_voting_tab(self):
        frame = self.voting_tab

        question_select_frame = ttk.LabelFrame(frame, text="Seleccionar Pregunta para Votación", padding=10)
        question_select_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(question_select_frame, text="Pregunta:").pack(side=tk.LEFT, padx=5)
        self.voting_question_combobox = ttk.Combobox(question_select_frame, state="readonly", width=60)
        self.voting_question_combobox.pack(side=tk.LEFT, padx=5)
        self.voting_question_combobox.bind("<<ComboboxSelected>>", self.on_voting_question_selected_for_display)

        ttk.Button(question_select_frame, text="Activar Pregunta para Votar",
                   command=self.activate_question_for_voting).pack(side=tk.LEFT, padx=5)
        ttk.Button(question_select_frame, text="Cerrar Votación Pregunta Actual",
                   command=self.close_current_question_voting).pack(side=tk.LEFT, padx=5)

        self.active_question_label = ttk.Label(frame, text="Pregunta Activa: Ninguna", font=("Arial", 12, "bold"))
        self.active_question_label.pack(pady=10)

        vote_entry_frame = ttk.LabelFrame(frame, text="Registrar Voto (Entrada Manual)", padding=10)
        vote_entry_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(vote_entry_frame, text="Residente Votante:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.voting_resident_combobox = ttk.Combobox(vote_entry_frame, state="readonly", width=40)
        self.voting_resident_combobox.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(vote_entry_frame, text="Opción de Voto:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.vote_option_var = tk.IntVar()
        options_frame = ttk.Frame(vote_entry_frame)
        ttk.Radiobutton(options_frame, text="1. Acepta", variable=self.vote_option_var, value=1).pack(side=tk.LEFT)
        ttk.Radiobutton(options_frame, text="2. No Acepta", variable=self.vote_option_var, value=2).pack(side=tk.LEFT,
                                                                                                         padx=10)
        ttk.Radiobutton(options_frame, text="3. En Blanco", variable=self.vote_option_var, value=3).pack(side=tk.LEFT)
        options_frame.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        ttk.Button(vote_entry_frame, text="Registrar Voto", command=self.register_vote).grid(row=2, column=0,
                                                                                             columnspan=2, pady=10)

        results_frame = ttk.LabelFrame(frame, text="Resultados de la Pregunta", padding=10)
        results_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.results_display_frame = results_frame
        self.results_canvas_widget = None

    def load_questions_for_voting_tab(self):
        """Carga las preguntas de la asamblea actual en el combobox de la pestaña de votación."""
        if not self.current_assembly_id:
            self.voting_question_combobox['values'] = []
            self.voting_question_combobox.set('')
            return

        questions = self.execute_query(
            "SELECT id, texto_pregunta FROM preguntas WHERE asamblea_id = ? ORDER BY id",
            (self.current_assembly_id,), fetchall=True
        )
        self.voting_question_combobox['values'] = [f"{q[0]}: {q[1]}" for q in questions]
        if questions:
            self.voting_question_combobox.current(0)
            self.on_voting_question_selected_for_display()  # Mostrar resultados de la primera pregunta por defecto
        else:
            self.voting_question_combobox.set('')
            if hasattr(self,
                       'results_canvas_widget') and self.results_canvas_widget:  # Limpiar gráfico si no hay preguntas
                self.results_canvas_widget.get_tk_widget().destroy()
                self.results_canvas_widget = None
                ttk.Label(self.results_display_frame, text="No hay preguntas para esta asamblea.").pack(pady=20)

    def on_voting_question_selected_for_display(self, event=None):
        """Cuando se selecciona una pregunta en el combobox de votación, muestra sus resultados (si los hay)."""
        selection = self.voting_question_combobox.get()
        if selection:
            try:
                question_id_to_display = int(selection.split(":")[0])
                self.display_vote_results_for_question(question_id_to_display)
            except ValueError:
                messagebox.showerror("Error", "Formato de selección de pregunta inválido.")

    def activate_question_for_voting(self):
        """Activa la pregunta seleccionada en el combobox para la votación."""
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

        # Desactivar cualquier otra pregunta que pudiera estar activa para esta asamblea
        if self.current_question_id is not None and self.current_question_id != new_active_question_id:
            self.execute_query("UPDATE preguntas SET activa = 0 WHERE id = ? AND asamblea_id = ?",
                               (self.current_question_id, self.current_assembly_id), commit=True)

        # Activar la nueva pregunta
        self.execute_query("UPDATE preguntas SET activa = 1 WHERE id = ? AND asamblea_id = ?",
                           (new_active_question_id, self.current_assembly_id), commit=True)

        self.current_question_id = new_active_question_id  # Actualizar el ID de la pregunta activa globalmente
        question_text = selection.split(":", 1)[1].strip()

        self.active_question_label.config(text=f"Pregunta Activa (ID: {self.current_question_id}): {question_text}")

        self.load_eligible_voters()  # Cargar/Recargar la lista de residentes que pueden votar
        self.display_vote_results_for_question(
            self.current_question_id)  # Mostrar resultados (probablemente vacíos al inicio)
        self.load_questions_for_assembly()  # Refrescar estado en la pestaña de asambleas
        messagebox.showinfo("Votación Activada", f"La pregunta '{question_text}' está activa para votación.")

    def close_current_question_voting(self):
        """Cierra la votación para la pregunta que está actualmente activa."""
        if not self.current_question_id:
            messagebox.showwarning("Advertencia", "Ninguna pregunta está activa para votación.")
            return

        question_id_to_close = self.current_question_id
        question_text_closed = self.execute_query("SELECT texto_pregunta FROM preguntas WHERE id = ?",
                                                  (question_id_to_close,), fetchone=True)

        self.execute_query("UPDATE preguntas SET activa = 0 WHERE id = ?", (question_id_to_close,), commit=True)
        self.load_questions_for_assembly()  # Refrescar estado en la pestaña de asambleas

        messagebox.showinfo("Votación Cerrada",
                            f"Se ha cerrado la votación para la pregunta: '{question_text_closed[0] if question_text_closed else 'ID ' + str(question_id_to_close)}'.")
        self.display_vote_results_for_question(question_id_to_close, final=True)  # Mostrar resultados finales

        self.current_question_id = None
        self.active_question_label.config(text="Pregunta Activa: Ninguna")
        self.voting_resident_combobox.set('')  # Limpiar votante
        self.voting_resident_combobox['values'] = []  # Limpiar lista de votantes
        self.vote_option_var.set(0)  # Limpiar opción de voto

    def load_eligible_voters(self):
        """Carga los residentes que pueden votar en la pregunta activa (no han dado poder)."""
        if not self.current_assembly_id:
            self.voting_resident_combobox['values'] = []
            self.voting_resident_combobox.set('')
            return

        # Residentes activos que NO han otorgado poder en ESTA asamblea
        query = """
        SELECT r.id, r.nombre, r.casa 
        FROM residentes r
        WHERE r.activo = 1 AND r.id NOT IN (
            SELECT p.residente_da_poder_id 
            FROM poderes p 
            WHERE p.asamblea_id = ?
        )
        ORDER BY r.nombre
        """
        eligible_voters_data = self.execute_query(query, (self.current_assembly_id,), fetchall=True)

        eligible_voters_list = [f"{r_id}: {nombre} ({casa})" for r_id, nombre, casa in eligible_voters_data]

        self.voting_resident_combobox['values'] = eligible_voters_list
        if eligible_voters_list:
            self.voting_resident_combobox.current(0)
        else:
            self.voting_resident_combobox.set('')

    def register_vote(self):
        if not self.current_question_id:
            messagebox.showerror("Error", "Ninguna pregunta está activa para votación. Por favor, active una pregunta.")
            return

        voter_selection = self.voting_resident_combobox.get()
        vote_option = self.vote_option_var.get()

        if not voter_selection:
            messagebox.showerror("Error", "Seleccione el residente que está votando.")
            return
        if vote_option == 0:
            messagebox.showerror("Error", "Seleccione una opción de voto (1, 2, o 3).")
            return

        try:
            resident_votante_id = int(voter_selection.split(":")[0])

            existing_vote = self.execute_query(
                "SELECT id FROM votos WHERE pregunta_id = ? AND residente_votante_id = ?",
                (self.current_question_id, resident_votante_id), fetchone=True
            )
            if existing_vote:
                if messagebox.askyesno("Confirmar Cambio de Voto",
                                       "Este residente ya ha votado por esta pregunta. ¿Desea cambiar el voto?"):
                    self.execute_query(
                        "UPDATE votos SET opcion_voto = ? WHERE pregunta_id = ? AND residente_votante_id = ?",
                        (vote_option, self.current_question_id, resident_votante_id), commit=True
                    )
                    messagebox.showinfo("Éxito", "Voto actualizado.")
                else:
                    return
            else:
                self.execute_query(
                    "INSERT INTO votos (pregunta_id, residente_votante_id, opcion_voto) VALUES (?, ?, ?)",
                    (self.current_question_id, resident_votante_id, vote_option), commit=True)
                messagebox.showinfo("Éxito", "Voto registrado.")

            self.display_vote_results_for_question(
                self.current_question_id)  # Actualizar gráfico para la pregunta activa
            self.vote_option_var.set(0)  # Resetear opción de voto
            # Opcional: Mover al siguiente residente en el combobox o limpiarlo.
            # self.voting_resident_combobox.set('')

        except ValueError:
            messagebox.showerror("Error", "Selección de residente inválida para registrar voto.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo registrar el voto: {e}")

    def get_voting_weights(self):
        """Calcula el peso de voto para cada residente que puede votar en la asamblea actual."""
        if not self.current_assembly_id:
            return {}

        weights = {}

        # Residentes activos que pueden votar (no han dado poder para esta asamblea)
        residents_can_vote = self.execute_query(
            """SELECT r.id FROM residentes r
               WHERE r.activo = 1 AND r.id NOT IN (
                   SELECT p.residente_da_poder_id FROM poderes p WHERE p.asamblea_id = ?
               )""",
            (self.current_assembly_id,), fetchall=True
        )
        for r_id_tuple in residents_can_vote:
            r_id = r_id_tuple[0]
            weights[r_id] = 1  # Peso base es 1 (una unidad/propiedad)

        # Sumar poderes a los residentes que los reciben
        proxies_received = self.execute_query(
            """SELECT residente_recibe_poder_id, COUNT(residente_da_poder_id) 
               FROM poderes 
               WHERE asamblea_id = ? 
               GROUP BY residente_recibe_poder_id""",
            (self.current_assembly_id,), fetchall=True
        )
        for receiver_id, count in proxies_received:
            # El receptor debe ser un residente activo y no haber dado su propio poder para que su voto cuente
            # Esta verificación ya está implícita en `residents_can_vote` para el peso base.
            # Aquí solo sumamos los poderes que recibió.
            if receiver_id in weights:
                weights[receiver_id] += count
            # else:
            # Si un residente que dio su poder (y por ende no está en 'weights' inicialmente)
            # recibe poderes de otros, esos poderes no se contarían si él no puede votar.
            # La lógica actual asume que quien recibe el poder también puede votar por sí mismo.
            # Si un residente que dio poder recibe poderes, su voto no se registra por la UI.
            # Para que los poderes cuenten, el receptor debe estar en la lista de `voting_resident_combobox`.
        return weights

    def display_vote_results_for_question(self, question_id_for_results, final=False):
        """Muestra los resultados para un ID de pregunta específico."""
        if not self.current_assembly_id:  # Necesitamos una asamblea para calcular pesos
            messagebox.showwarning("Advertencia", "No hay una asamblea seleccionada para calcular pesos de votación.")
            return
        if not question_id_for_results:
            # Limpiar gráfico si no hay pregunta
            if hasattr(self, 'results_canvas_widget') and self.results_canvas_widget:
                self.results_canvas_widget.get_tk_widget().destroy()
                self.results_canvas_widget = None
            for widget in self.results_display_frame.winfo_children():
                widget.destroy()
            ttk.Label(self.results_display_frame, text="Seleccione una pregunta para ver sus resultados.").pack(pady=20)
            return

        # Limpiar gráfico anterior si existe
        if hasattr(self, 'results_canvas_widget') and self.results_canvas_widget:
            self.results_canvas_widget.get_tk_widget().destroy()
            self.results_canvas_widget = None
        for widget in self.results_display_frame.winfo_children():
            widget.destroy()

        votes_data = self.execute_query(
            "SELECT residente_votante_id, opcion_voto FROM votos WHERE pregunta_id = ?",
            (question_id_for_results,), fetchall=True
        )

        question_info = self.execute_query("SELECT texto_pregunta, activa FROM preguntas WHERE id = ?",
                                           (question_id_for_results,), fetchone=True)
        q_text = question_info[0] if question_info else f"Pregunta ID {question_id_for_results}"
        q_is_active_in_db = question_info[1] == 1 if question_info else False

        if not votes_data:
            ttk.Label(self.results_display_frame, text=f"Aún no hay votos registrados para:\n'{q_text}'").pack(pady=20)
            return

        # Obtener los pesos de votación para la asamblea actual.
        # Estos pesos se aplican al `residente_votante_id` que está en la tabla `votos`.
        voting_weights_for_assembly = self.get_voting_weights()

        weighted_results = Counter()  # {1: total_weight_yes, 2: total_weight_no, 3: total_weight_abstain}

        for resident_id_who_voted, option in votes_data:
            # El `resident_id_who_voted` es el ID del residente que ejerció el voto
            # (que ya incluye su propio voto + los poderes que representa si los tiene).
            # Su peso total se busca en `voting_weights_for_assembly`.
            weight_of_this_voter_event = voting_weights_for_assembly.get(resident_id_who_voted, 0)
            # Si un residente votó pero luego se inactivó o se le quitó un poder, su peso aquí podría ser 0.
            # Esto es correcto, ya que el peso se calcula en el momento de mostrar los resultados.

            weighted_results[option] += weight_of_this_voter_event

        total_weighted_votes_cast = sum(weighted_results.values())

        labels_map = {1: 'Acepta', 2: 'No Acepta', 3: 'En Blanco'}
        chart_labels = []
        chart_sizes = []

        raw_counts_display = {}  # Para mostrar el número de votantes individuales

        for option_key in sorted(weighted_results.keys()):
            total_weight_for_option = weighted_results[option_key]
            option_text_label = labels_map.get(option_key, 'Desconocido')

            # Contar votos individuales (cuántas "entidades votantes" eligieron esta opción)
            count_for_option = sum(1 for r_id, o in votes_data if o == option_key)
            raw_counts_display[option_text_label] = count_for_option

            if total_weighted_votes_cast > 0:
                percentage = (total_weight_for_option / total_weighted_votes_cast) * 100
                chart_labels.append(f"{option_text_label}\n({total_weight_for_option} pesos, {percentage:.1f}%)")
            else:
                chart_labels.append(f"{option_text_label}\n({total_weight_for_option} pesos)")
            chart_sizes.append(total_weight_for_option)

        if not chart_sizes or all(s == 0 for s in chart_sizes):  # Si no hay votos con peso
            ttk.Label(self.results_display_frame,
                      text=f"No hay votos con peso válidos para graficar para:\n'{q_text}'").pack(pady=20)
            return

        fig, ax = plt.subplots(figsize=(6, 4))  # Ajustar tamaño del gráfico

        wedges, texts, autotexts = ax.pie(
            chart_sizes,
            labels=None,
            autopct=lambda p: '{:.1f}%'.format(p) if p > 0 and total_weighted_votes_cast > 0 else '',
            startangle=90,
            pctdistance=0.85,
            wedgeprops=dict(width=0.4)  # Para efecto dona
        )
        ax.axis('equal')

        # Leyenda con los chart_labels que ya tienen el peso y el porcentaje
        ax.legend(wedges, chart_labels, title="Opciones de Voto", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        plt.subplots_adjust(left=0.1, right=0.70)  # Ajustar para dar espacio a la leyenda

        title_text = f"Resultados: {q_text}"
        if final:  # Si la votación de esta pregunta se cerró explícitamente
            title_text = f"Resultados Finales: {q_text}"
        # Si la pregunta mostrada es la que está activa para votación en la app
        elif self.current_question_id == question_id_for_results and q_is_active_in_db:
            title_text = f"Resultados Parciales: {q_text} (Votación Abierta)"
        # Si la pregunta no está marcada como activa en la DB (votación cerrada previamente)
        elif not q_is_active_in_db:
            title_text = f"Resultados (Votación Cerrada): {q_text}"

        plt.title(title_text, pad=20, loc='center', fontsize=10)

        # Información adicional debajo del gráfico
        info_text_lines = [f"Pregunta ID: {question_id_for_results}"]
        info_text_lines.append("\nConteo de votos (número de votantes, no ponderado):")
        for opt_text, count in raw_counts_display.items():
            info_text_lines.append(f"- {opt_text}: {count} votante{'s' if count != 1 else ''}")

        info_text_lines.append(f"\nTotal de peso de votos emitidos: {total_weighted_votes_cast}")

        # Calcular el total de peso posible en la asamblea basado en los residentes elegibles y sus poderes
        total_possible_weight_in_assembly = sum(voting_weights_for_assembly.values())
        info_text_lines.append(
            f"Total de peso posible en la asamblea (votantes elegibles): {total_possible_weight_in_assembly}")

        if total_possible_weight_in_assembly > 0:
            participation_percentage = (total_weighted_votes_cast / total_possible_weight_in_assembly) * 100
            info_text_lines.append(
                f"Participación (basada en peso emitido vs. peso posible): {participation_percentage:.1f}%")

        ttk.Label(self.results_display_frame, text="\n".join(info_text_lines), justify=tk.LEFT, wraplength=350).pack(
            pady=10, anchor='w', padx=10)

        canvas = FigureCanvasTkAgg(fig, master=self.results_display_frame)
        canvas.draw()
        self.results_canvas_widget = canvas.get_tk_widget()
        self.results_canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        plt.close(fig)  # Liberar memoria de la figura


# --- Main ---
if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
