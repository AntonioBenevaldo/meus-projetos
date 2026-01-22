
ANÁLISE DE DADOS COM INTERFACE GRÁFICA (GUI) COMPLETA
Autor: Assistente Python
Descrição: Aplicação completa para análise exploratória de dados com visualização interativa
"""

import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import seaborn as sns
import warnings
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

# PyQt5 imports
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

warnings.filterwarnings('ignore')

# Configurar estilo dos gráficos
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

class MplCanvas(FigureCanvas):
    """Canvas para matplotlib integrado ao PyQt5"""
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        super(MplCanvas, self).__init__(self.fig)
        self.setParent(parent)

class DataAnalysisApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.df = None
        self.current_plot_type = "histogram"
        self.initUI()
        
    def initUI(self):
        """Inicializa a interface gráfica"""
        self.setWindowTitle("Analise de Dados - GUI Completa")
        self.setGeometry(100, 100, 1400, 900)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # ==============================================
        # PAINEL ESQUERDO - CONTROLES
        # ==============================================
        left_panel = QWidget()
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        
        # Grupo: Carregar Dados
        group_load = QGroupBox("Carregar Dados")
        load_layout = QVBoxLayout()
        
        self.btn_load_csv = QPushButton("Carregar Arquivo CSV")
        self.btn_load_csv.clicked.connect(self.load_csv)
        self.btn_load_csv.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        self.btn_sample_data = QPushButton("Usar Dados de Exemplo (Boston)")
        self.btn_sample_data.clicked.connect(self.load_sample_data)
        self.btn_sample_data.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        
        self.label_file = QLabel("Nenhum arquivo carregado")
        self.label_file.setStyleSheet("color: #666; font-style: italic;")
        
        load_layout.addWidget(self.btn_load_csv)
        load_layout.addWidget(self.btn_sample_data)
        load_layout.addWidget(self.label_file)
        load_layout.addStretch()
        group_load.setLayout(load_layout)
        
        # Grupo: Informacoes do Dataset
        self.group_info = QGroupBox("Informacoes do Dataset")
        self.group_info.setVisible(False)
        info_layout = QVBoxLayout()
        
        self.label_shape = QLabel("Shape: ")
        self.label_columns = QLabel("Colunas: ")
        self.label_missing = QLabel("Valores nulos: ")
        
        info_layout.addWidget(self.label_shape)
        info_layout.addWidget(self.label_columns)
        info_layout.addWidget(self.label_missing)
        info_layout.addStretch()
        self.group_info.setLayout(info_layout)
        
        # Grupo: Selecao de Variaveis
        self.group_variables = QGroupBox("Selecao de Variaveis")
        self.group_variables.setVisible(False)
        var_layout = QVBoxLayout()
        
        # Variavel X
        var_x_layout = QHBoxLayout()
        var_x_layout.addWidget(QLabel("Variavel X:"))
        self.combo_x = QComboBox()
        var_x_layout.addWidget(self.combo_x)
        
        # Variavel Y (para graficos de dispersao)
        var_y_layout = QHBoxLayout()
        var_y_layout.addWidget(QLabel("Variavel Y:"))
        self.combo_y = QComboBox()
        var_y_layout.addWidget(self.combo_y)
        
        # Variavel Target (para regressao)
        var_target_layout = QHBoxLayout()
        var_target_layout.addWidget(QLabel("Target (Regressao):"))
        self.combo_target = QComboBox()
        var_target_layout.addWidget(self.combo_target)
        
        var_layout.addLayout(var_x_layout)
        var_layout.addLayout(var_y_layout)
        var_layout.addLayout(var_target_layout)
        self.group_variables.setLayout(var_layout)
        
        # Grupo: Tipo de Analise
        self.group_analysis = QGroupBox("Tipo de Analise")
        self.group_analysis.setVisible(False)
        analysis_layout = QVBoxLayout()
        
        # Botoes de tipo de grafico
        self.btn_hist = QPushButton("Histograma")
        self.btn_hist.clicked.connect(lambda: self.update_plot("histogram"))
        self.btn_hist.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                padding: 8px;
                border-radius: 5px;
                text-align: left;
                padding-left: 15px;
            }
            QPushButton:hover {
                background-color: #7B1FA2;
            }
        """)
        
        self.btn_scatter = QPushButton("Grafico de Dispersao")
        self.btn_scatter.clicked.connect(lambda: self.update_plot("scatter"))
        self.btn_scatter.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px;
                border-radius: 5px;
                text-align: left;
                padding-left: 15px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        
        self.btn_boxplot = QPushButton("Boxplot")
        self.btn_boxplot.clicked.connect(lambda: self.update_plot("boxplot"))
        self.btn_boxplot.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 8px;
                border-radius: 5px;
                text-align: left;
                padding-left: 15px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        
        self.btn_correlation = QPushButton("Matriz de Correlacao")
        self.btn_correlation.clicked.connect(lambda: self.update_plot("correlation"))
        self.btn_correlation.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px;
                border-radius: 5px;
                text-align: left;
                padding-left: 15px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        self.btn_regression = QPushButton("Regressao Linear")
        self.btn_regression.clicked.connect(lambda: self.update_plot("regression"))
        self.btn_regression.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                padding: 8px;
                border-radius: 5px;
                text-align: left;
                padding-left: 15px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        
        analysis_layout.addWidget(self.btn_hist)
        analysis_layout.addWidget(self.btn_scatter)
        analysis_layout.addWidget(self.btn_boxplot)
        analysis_layout.addWidget(self.btn_correlation)
        analysis_layout.addWidget(self.btn_regression)
        analysis_layout.addStretch()
        self.group_analysis.setLayout(analysis_layout)
        
        # Grupo: Estatisticas
        self.group_stats = QGroupBox("Estatisticas Descritivas")
        self.group_stats.setVisible(False)
        stats_layout = QVBoxLayout()
        
        self.text_stats = QTextEdit()
        self.text_stats.setReadOnly(True)
        self.text_stats.setMaximumHeight(200)
        stats_layout.addWidget(self.text_stats)
        self.group_stats.setLayout(stats_layout)
        
        # Grupo: Acoes
        self.group_actions = QGroupBox("Acoes")
        self.group_actions.setVisible(False)
        actions_layout = QVBoxLayout()
        
        self.btn_export = QPushButton("Exportar Relatorio")
        self.btn_export.clicked.connect(self.export_report)
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #455A64;
            }
        """)
        
        self.btn_clear = QPushButton("Limpar Analise")
        self.btn_clear.clicked.connect(self.clear_analysis)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        
        actions_layout.addWidget(self.btn_export)
        actions_layout.addWidget(self.btn_clear)
        actions_layout.addStretch()
        self.group_actions.setLayout(actions_layout)
        
        # Adicionar grupos ao painel esquerdo
        left_layout.addWidget(group_load)
        left_layout.addWidget(self.group_info)
        left_layout.addWidget(self.group_variables)
        left_layout.addWidget(self.group_analysis)
        left_layout.addWidget(self.group_stats)
        left_layout.addWidget(self.group_actions)
        left_layout.addStretch()
        
        # ==============================================
        # PAINEL DIREITO - VISUALIZACAO
        # ==============================================
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)
        
        # Canvas para matplotlib
        self.canvas = MplCanvas(self, width=10, height=8, dpi=100)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        # Area de texto para resultados
        self.text_results = QTextEdit()
        self.text_results.setReadOnly(True)
        self.text_results.setMaximumHeight(250)
        self.text_results.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Courier New', monospace;
            }
        """)
        
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas)
        right_layout.addWidget(self.text_results)
        
        # Adicionar paineis ao layout principal
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 3)
        
        # Status bar
        self.statusBar().showMessage('Pronto para carregar dados')
        
        # Aplicar estilo geral
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QLabel {
                color: #333;
            }
            QComboBox {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
            }
            QComboBox:hover {
                border: 1px solid #888;
            }
        """)
        
    def load_csv(self):
        """Carrega um arquivo CSV"""
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Carregar Arquivo CSV", "", 
            "CSV Files (*.csv);;All Files (*)", 
            options=options
        )
        
        if file_name:
            try:
                self.df = pd.read_csv(file_name)
                self.initialize_analysis()
                self.label_file.setText(f"Arquivo: {os.path.basename(file_name)}")
                self.statusBar().showMessage(f'Dataset carregado: {self.df.shape[0]} linhas, {self.df.shape[1]} colunas')
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao carregar arquivo: {str(e)}")
    
    def load_sample_data(self):
        """Carrega dados de exemplo (Boston Housing)"""
        try:
            from sklearn.datasets import fetch_openml
            boston = fetch_openml(name='boston', version=1, as_frame=True)
            self.df = boston.frame
            self.initialize_analysis()
            self.label_file.setText("Dados de Exemplo: Boston Housing")
            self.statusBar().showMessage(f'Dataset de exemplo carregado: {self.df.shape[0]} linhas, {self.df.shape[1]} colunas')
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao carregar dados de exemplo: {str(e)}")
    
    def initialize_analysis(self):
        """Inicializa a analise apos carregar dados"""
        if self.df is not None:
            # Atualizar informacoes do dataset
            self.label_shape.setText(f"Shape: {self.df.shape[0]} linhas x {self.df.shape[1]} colunas")
            col_text = ', '.join(self.df.columns[:5])
            if len(self.df.columns) > 5:
                col_text += '...'
            self.label_columns.setText(f"Colunas: {col_text}")
            
            missing = self.df.isnull().sum().sum()
            self.label_missing.setText(f"Valores nulos: {missing}")
            
            # Preencher comboboxes com colunas numericas
            numeric_cols = self.df.select_dtypes(include=[np.number]).columns.tolist()
            
            self.combo_x.clear()
            self.combo_y.clear()
            self.combo_target.clear()
            
            for col in numeric_cols:
                self.combo_x.addItem(col)
                self.combo_y.addItem(col)
                self.combo_target.addItem(col)
            
            # Selecionar primeiras colunas como padrao
            if len(numeric_cols) >= 2:
                self.combo_x.setCurrentIndex(0)
                self.combo_y.setCurrentIndex(1)
                self.combo_target.setCurrentIndex(len(numeric_cols)-1 if len(numeric_cols) > 0 else 0)
            
            # Mostrar grupos de controle
            self.group_info.setVisible(True)
            self.group_variables.setVisible(True)
            self.group_analysis.setVisible(True)
            self.group_stats.setVisible(True)
            self.group_actions.setVisible(True)
            
            # Calcular e mostrar estatisticas iniciais
            self.update_statistics()
            
            # Plotar grafico inicial
            self.update_plot("histogram")
    
    def update_statistics(self):
        """Atualiza as estatisticas descritivas"""
        if self.df is not None and self.combo_x.currentText():
            col = self.combo_x.currentText()
            if col in self.df.columns:
                stats_text = f"Estatisticas para '{col}':\n"
                stats_text += "=" * 40 + "\n"
                
                # Estatisticas basicas
                stats_text += f"Media: {self.df[col].mean():.4f}\n"
                stats_text += f"Mediana: {self.df[col].median():.4f}\n"
                stats_text += f"Desvio Padrao: {self.df[col].std():.4f}\n"
                stats_text += f"Minimo: {self.df[col].min():.4f}\n"
                stats_text += f"Maximo: {self.df[col].max():.4f}\n"
                stats_text += f"Q1 (25%): {self.df[col].quantile(0.25):.4f}\n"
                stats_text += f"Q3 (75%): {self.df[col].quantile(0.75):.4f}\n"
                stats_text += f"IQR: {self.df[col].quantile(0.75) - self.df[col].quantile(0.25):.4f}\n"
                stats_text += f"Assimetria: {self.df[col].skew():.4f}\n"
                stats_text += f"Curtose: {self.df[col].kurtosis():.4f}\n"
                
                # Valores unicos e nulos
                stats_text += f"Valores unicos: {self.df[col].nunique()}\n"
                null_percent = self.df[col].isnull().sum()/len(self.df)*100
                stats_text += f"Valores nulos: {self.df[col].isnull().sum()} ({null_percent:.2f}%)\n"
                
                self.text_stats.setText(stats_text)
    
    def update_plot(self, plot_type):
        """Atualiza o grafico conforme o tipo selecionado"""
        if self.df is None:
            return
        
        self.current_plot_type = plot_type
        self.canvas.axes.clear()
        
        try:
            if plot_type == "histogram":
                self.plot_histogram()
            elif plot_type == "scatter":
                self.plot_scatter()
            elif plot_type == "boxplot":
                self.plot_boxplot()
            elif plot_type == "correlation":
                self.plot_correlation()
            elif plot_type == "regression":
                self.plot_regression()
            
            self.canvas.fig.tight_layout()
            self.canvas.draw()
            
        except Exception as e:
            self.text_results.setText(f"Erro ao gerar grafico: {str(e)}")
    
    def plot_histogram(self):
        """Plota histograma"""
        col = self.combo_x.currentText()
        if col not in self.df.columns:
            return
        
        # Limpar e preparar o grafico
        self.canvas.axes.clear()
        
        # Plotar histograma
        n_bins = min(30, len(self.df[col].dropna().unique()))
        self.df[col].dropna().hist(ax=self.canvas.axes, bins=n_bins, edgecolor='black', alpha=0.7)
        
        # Adicionar linhas de media e mediana
        mean_val = self.df[col].mean()
        median_val = self.df[col].median()
        
        self.canvas.axes.axvline(mean_val, color='red', linestyle='--', linewidth=2, label=f'Media: {mean_val:.2f}')
        self.canvas.axes.axvline(median_val, color='green', linestyle='--', linewidth=2, label=f'Mediana: {median_val:.2f}')
        
        # Configuracoes do grafico
        self.canvas.axes.set_title(f'Histograma de {col}')
        self.canvas.axes.set_xlabel(col)
        self.canvas.axes.set_ylabel('Frequencia')
        self.canvas.axes.legend()
        self.canvas.axes.grid(True, alpha=0.3)
        
        # Atualizar resultados
        skewness = self.df[col].skew()
        kurt = self.df[col].kurtosis()
        
        results_text = f"ANALISE DE DISTRIBUICAO - {col}\n"
        results_text += "=" * 50 + "\n"
        results_text += f"Media: {mean_val:.4f}\n"
        results_text += f"Mediana: {median_val:.4f}\n"
        results_text += f"Desvio Padrao: {self.df[col].std():.4f}\n"
        results_text += f"Assimetria (Skewness): {skewness:.4f}\n"
        
        if abs(skewness) < 0.5:
            results_text += "  -> Distribuicao aproximadamente simetrica\n"
        elif skewness > 0:
            results_text += "  -> Distribuicao assimetrica positiva (vies a direita)\n"
        else:
            results_text += "  -> Distribuicao assimetrica negativa (vies a esquerda)\n"
        
        results_text += f"Curtose: {kurt:.4f}\n"
        if kurt > 0:
            results_text += "  -> Distribuicao leptocurtica (picos mais altos, caudas pesadas)\n"
        elif kurt < 0:
            results_text += "  -> Distribuicao platicurtica (picos mais baixos, caudas leves)\n"
        else:
            results_text += "  -> Distribuicao mesocurtica (similar a normal)\n"
        
        self.text_results.setText(results_text)
        self.update_statistics()
    
    def plot_scatter(self):
        """Plota grafico de dispersao"""
        col_x = self.combo_x.currentText()
        col_y = self.combo_y.currentText()
        
        if col_x not in self.df.columns or col_y not in self.df.columns:
            return
        
        # Limpar e preparar o grafico
        self.canvas.axes.clear()
        
        # Plotar grafico de dispersao
        self.canvas.axes.scatter(self.df[col_x], self.df[col_y], alpha=0.6, edgecolors='w', linewidth=0.5)
        
        # Calcular e plotar linha de tendencia
        mask = ~self.df[[col_x, col_y]].isnull().any(axis=1)
        if mask.sum() > 1:
            x_vals = self.df.loc[mask, col_x].values.reshape(-1, 1)
            y_vals = self.df.loc[mask, col_y].values
            
            # Regressao linear simples
            model = LinearRegression()
            model.fit(x_vals, y_vals)
            y_pred = model.predict(x_vals)
            
            # Plotar linha de regressao
            self.canvas.axes.plot(self.df.loc[mask, col_x], y_pred, color='red', 
                                 linewidth=2, label='Linha de Regressao')
        
        # Configuracoes do grafico
        self.canvas.axes.set_title(f'{col_y} vs {col_x}')
        self.canvas.axes.set_xlabel(col_x)
        self.canvas.axes.set_ylabel(col_y)
        self.canvas.axes.legend()
        self.canvas.axes.grid(True, alpha=0.3)
        
        # Calcular correlacao
        correlation = self.df[[col_x, col_y]].corr().iloc[0, 1]
        
        # Atualizar resultados
        results_text = f"ANALISE DE CORRELACAO\n"
        results_text += "=" * 50 + "\n"
        results_text += f"Variavel X: {col_x}\n"
        results_text += f"Variavel Y: {col_y}\n"
        results_text += f"Coeficiente de Correlacao (Pearson): {correlation:.4f}\n"
        
        if abs(correlation) > 0.7:
            results_text += "  -> Correlacao FORTE\n"
        elif abs(correlation) > 0.3:
            results_text += "  -> Correlacao MODERADA\n"
        else:
            results_text += "  -> Correlacao FRACA\n"
        
        if correlation > 0:
            results_text += "  -> Relacao POSITIVA (quando X aumenta, Y tende a aumentar)\n"
        else:
            results_text += "  -> Relacao NEGATIVA (quando X aumenta, Y tende a diminuir)\n"
        
        if mask.sum() > 1:
            results_text += f"\nREGRESSAO LINEAR SIMPLES:\n"
            results_text += f"Inclinacao (coeficiente): {model.coef_[0]:.4f}\n"
            results_text += f"Intercepto: {model.intercept_:.4f}\n"
            results_text += f"Equacao: y = {model.coef_[0]:.4f}x + {model.intercept_:.4f}\n"
        
        self.text_results.setText(results_text)
    
    def plot_boxplot(self):
        """Plota boxplot"""
        col = self.combo_x.currentText()
        if col not in self.df.columns:
            return
        
        # Limpar e preparar o grafico
        self.canvas.axes.clear()
        
        # Plotar boxplot
        boxplot_data = self.df[col].dropna()
        self.canvas.axes.boxplot(boxplot_data, vert=True, patch_artist=True,
                               boxprops=dict(facecolor='lightblue', color='blue'),
                               medianprops=dict(color='red', linewidth=2),
                               whiskerprops=dict(color='blue'),
                               capprops=dict(color='blue'),
                               flierprops=dict(marker='o', color='red', alpha=0.5))
        
        # Configuracoes do grafico
        self.canvas.axes.set_title(f'Boxplot de {col}')
        self.canvas.axes.set_ylabel(col)
        self.canvas.axes.grid(True, alpha=0.3)
        
        # Calcular estatisticas do boxplot
        q1 = boxplot_data.quantile(0.25)
        q3 = boxplot_data.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        outliers = boxplot_data[(boxplot_data < lower_bound) | (boxplot_data > upper_bound)]
        
        # Atualizar resultados
        results_text = f"ANALISE BOXPLOT - {col}\n"
        results_text += "=" * 50 + "\n"
        results_text += f"Q1 (25o percentil): {q1:.4f}\n"
        results_text += f"Q3 (75o percentil): {q3:.4f}\n"
        results_text += f"IQR (Q3 - Q1): {iqr:.4f}\n"
        results_text += f"Limite inferior: {lower_bound:.4f}\n"
        results_text += f"Limite superior: {upper_bound:.4f}\n"
        results_text += f"Minimo (dentro dos limites): {boxplot_data[boxplot_data >= lower_bound].min():.4f}\n"
        results_text += f"Maximo (dentro dos limites): {boxplot_data[boxplot_data <= upper_bound].max():.4f}\n"
        results_text += f"Numero de outliers: {len(outliers)}\n"
        
        if len(outliers) > 0:
            outlier_values = [f'{x:.2f}' for x in outliers.head(10).values]
            results_text += f"Outliers: {', '.join(outlier_values)}"
            if len(outliers) > 10:
                results_text += f"... (mais {len(outliers) - 10})"
        
        self.text_results.setText(results_text)
    
    def plot_correlation(self):
        """Plota matriz de correlacao"""
        # Selecionar apenas colunas numericas
        numeric_df = self.df.select_dtypes(include=[np.number])
        
        if numeric_df.shape[1] < 2:
            self.text_results.setText("Erro: E necessario pelo menos 2 variaveis numericas para a matriz de correlacao.")
            return
        
        # Limpar e preparar o grafico
        self.canvas.axes.clear()
        
        # Calcular matriz de correlacao
        corr_matrix = numeric_df.corr()
        
        # Plotar heatmap
        im = self.canvas.axes.imshow(corr_matrix.values, cmap='coolwarm', vmin=-1, vmax=1, aspect='auto')
        
        # Configurar ticks
        self.canvas.axes.set_xticks(range(len(corr_matrix.columns)))
        self.canvas.axes.set_yticks(range(len(corr_matrix.columns)))
        self.canvas.axes.set_xticklabels(corr_matrix.columns, rotation=45, ha='right')
        self.canvas.axes.set_yticklabels(corr_matrix.columns)
        
        # Adicionar valores na matriz
        for i in range(len(corr_matrix.columns)):
            for j in range(len(corr_matrix.columns)):
                value = corr_matrix.iloc[i, j]
                color = 'white' if abs(value) > 0.5 else 'black'
                self.canvas.axes.text(j, i, f'{value:.2f}', 
                                     ha='center', va='center', color=color, fontsize=9)
        
        # Adicionar barra de cores
        plt.colorbar(im, ax=self.canvas.axes)
        
        # Configuracoes do grafico
        self.canvas.axes.set_title('Matriz de Correlacao')
        
        # Encontrar correlacoes mais fortes
        strong_correlations = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                col1 = corr_matrix.columns[i]
                col2 = corr_matrix.columns[j]
                corr_value = corr_matrix.iloc[i, j]
                if abs(corr_value) > 0.5:  # Correlacao forte
                    strong_correlations.append((col1, col2, corr_value))
        
        # Ordenar por valor absoluto
        strong_correlations.sort(key=lambda x: abs(x[2]), reverse=True)
        
        # Atualizar resultados
        results_text = "MATRIZ DE CORRELACAO\n"
        results_text += "=" * 50 + "\n"
        results_text += f"Numero de variaveis numericas: {numeric_df.shape[1]}\n\n"
        
        results_text += "CORRELACOES MAIS FORTES:\n"
        if strong_correlations:
            for col1, col2, corr in strong_correlations[:10]:
                strength = "FORTE" if abs(corr) > 0.7 else "MODERADA"
                direction = "POSITIVA" if corr > 0 else "NEGATIVA"
                results_text += f"* {col1} <-> {col2}: {corr:.3f} ({strength}, {direction})\n"
        else:
            results_text += "Nenhuma correlacao forte encontrada (|r| > 0.5)\n"
        
        self.text_results.setText(results_text)
    
    def plot_regression(self):
        """Plota regressao linear e mostra metricas"""
        col_x = self.combo_x.currentText()
        col_y = self.combo_target.currentText()
        
        if col_x not in self.df.columns or col_y not in self.df.columns:
            return
        
        # Limpar e preparar o grafico
        self.canvas.axes.clear()
        
        # Preparar dados para regressao
        data = self.df[[col_x, col_y]].dropna()
        if len(data) < 2:
            self.text_results.setText("Erro: Dados insuficientes para regressao.")
            return
        
        X = data[col_x].values.reshape(-1, 1)
        y = data[col_y].values
        
        # Dividir em treino e teste
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Treinar modelo
        model = LinearRegression()
        model.fit(X_train, y_train)
        
        # Fazer previsoes
        y_pred = model.predict(X_test)
        
        # Plotar dados e linha de regressao
        self.canvas.axes.scatter(X, y, alpha=0.6, label='Dados reais')
        
        # Plotar linha de regressao
        x_line = np.linspace(X.min(), X.max(), 100).reshape(-1, 1)
        y_line = model.predict(x_line)
        self.canvas.axes.plot(x_line, y_line, color='red', linewidth=3, label='Linha de regressao')
        
        # Configuracoes do grafico
        self.canvas.axes.set_title(f'Regressao Linear: {col_y} = f({col_x})')
        self.canvas.axes.set_xlabel(col_x)
        self.canvas.axes.set_ylabel(col_y)
        self.canvas.axes.legend()
        self.canvas.axes.grid(True, alpha=0.3)
        
        # Calcular metricas
        mse = mean_squared_error(y_test, y_pred)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        
        # Calcular estatisticas dos residuos
        residuals = y_test - y_pred
        
        # Atualizar resultados
        results_text = f"REGRESSAO LINEAR - {col_y} vs {col_x}\n"
        results_text += "=" * 50 + "\n"
        results_text += f"Tamanho da amostra: {len(data)} observacoes\n"
        results_text += f"Divisao treino/teste: {len(X_train)}/{len(X_test)}\n\n"
        
        results_text += "PARAMETROS DO MODELO:\n"
        results_text += f"Coeficiente (inclinacao): {model.coef_[0]:.4f}\n"
        results_text += f"Intercepto: {model.intercept_:.4f}\n"
        results_text += f"Equacao: {col_y} = {model.coef_[0]:.4f} x {col_x} + {model.intercept_:.4f}\n\n"
        
        results_text += "METRICAS DE DESEMPENHO:\n"
        results_text += f"R2 (coeficiente de determinacao): {r2:.4f}\n"
        results_text += f"  -> Variacao explicada: {r2*100:.1f}%\n"
        results_text += f"Erro Quadratico Medio (MSE): {mse:.4f}\n"
        results_text += f"Raiz do MSE (RMSE): {rmse:.4f}\n"
        results_text += f"Erro Absoluto Medio (MAE): {mae:.4f}\n"
        
        self.text_results.setText(results_text)
    
    def export_report(self):
        """Exporta um relatorio da analise"""
        if self.df is None:
            QMessage