"""Схема архитектуры развёртывания: формирует 10_architecture.dot и PNG через graphviz."""
import subprocess

F = 'fontname="Liberation Serif"'
dot = f'''digraph A {{
graph [rankdir=TB nodesep=0.25 ranksep=0.35 dpi=150 {F} fontsize=20 forcelabels=true compound=true newrank=true pad=0.4];
node [{F} fontsize=20 shape=component style=filled fillcolor="#f0f0f0"];
edge [{F} fontsize=17 arrowsize=0.8];
subgraph cluster_c {{ label=<<B>Клиенты</B>>; style=solid;
  subgraph cluster_dev {{ label="Устройство пользователя"; style=solid; penwidth=1.5;
    Browser [shape=box3d label="Браузер"];
    Msg [shape=box3d label="Telegram /\\nВКонтакте"];
  }}
}}
subgraph cluster_pd {{ label=<<B>Граница обработки персональных данных (152-ФЗ)</B>>; style="dashed,bold"; penwidth=3;
  subgraph cluster_ru {{ label="Сервер в РФ (Ubuntu, Docker)"; style=solid; penwidth=1.5;
    Nginx [label="Nginx\\n(TLS, статика,\\n/api/bot/ только с IP бота)"];
    App [label="Веб-приложение FastAPI\\n(сайт, кабинет, API бота)"];
    Exp [label="Модуль методики\\n(экспертиза, прогноз,\\nитоговая оценка)"];
    DB [shape=cylinder label="PostgreSQL 16"];
    FS [shape=folder label="media/ (фото)\\nfiles/ (документы)"];
    Cron [label="cron: резервная копия,\\nочистка ПДн"];
  }}
}}
subgraph cluster_x {{ label=<<B>Внешние сервисы</B>>; style=solid;
  subgraph cluster_ext {{ label="Внешний сервер"; style=solid; penwidth=1.5;
    Bot [label="Бот (Python,\\nlong polling)"];
    N8N [label="n8n\\n(выгрузка в Google)"];
  }}
  MAPI [shape=ellipse label="Telegram Bot API /\\nVK Long Poll"];
  TP [shape=ellipse label="Timepad\\n(билеты, 54-ФЗ)"];
  GG [shape=ellipse label="Google Таблицы\\nи Документы"];
  GH [shape=ellipse label="GitHub Actions\\n(проверка, выкладка)"];
}}
L [shape=plain style="" fontsize=18 label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="4" CELLPADDING="3">
<TR><TD COLSPAN="2" ALIGN="LEFT"><B>Обозначения</B></TD></TR>
<TR><TD>рамка с подписью</TD><TD ALIGN="LEFT">сервер или устройство</TD></TR>
<TR><TD>прямоугольник с выступами</TD><TD ALIGN="LEFT">программный компонент</TD></TR>
<TR><TD>цилиндр</TD><TD ALIGN="LEFT">база данных</TD></TR>
<TR><TD>папка</TD><TD ALIGN="LEFT">файловое хранилище</TD></TR>
<TR><TD>овал</TD><TD ALIGN="LEFT">внешний интернет-сервис</TD></TR>
<TR><TD>жирная пунктирная рамка</TD><TD ALIGN="LEFT">граница обработки персональных данных</TD></TR>
<TR><TD>сплошная стрелка</TD><TD ALIGN="LEFT">обмен данными (подпись — протокол)</TD></TR>
<TR><TD>пунктирная стрелка</TD><TD ALIGN="LEFT">служебный доступ или обращение по требованию</TD></TR>
</TABLE>>];
{{rank=same; Browser; Bot; Nginx}}
{{rank=same; Msg; N8N; App}}
{{rank=same; MAPI; Exp; FS}}
{{rank=same; GG; DB; Cron}}
{{rank=same; TP; GH}}
{{rank=sink; L}}
Browser -> Msg [style=invis]; Bot -> N8N [style=invis]; N8N -> MAPI [style=invis]; MAPI -> GG [style=invis];
GG -> TP [style=invis]; TP -> GH [style=invis]; GH -> L [style=invis];
Nginx -> App [style=invis]; App -> Exp [style=invis]; Exp -> DB [style=invis];
Browser -> Nginx [label="HTTPS"];
Nginx -> App [label="HTTP (сеть Docker)"];
App -> Exp [label="вызов\\nфункций"];
App -> DB [label="SQL"];
Exp -> DB [label="SQL"];
App -> FS [label="файлы"];
DB -> Cron [label="pg_dump"];
Bot -> MAPI [label="HTTPS\\nlong polling" dir=both constraint=false];
Msg -> MAPI [label="HTTPS" constraint=false];
Bot -> Nginx [label="HTTPS /api/bot/*,\\nBearer-токен" constraint=false];
Nginx -> N8N [label="HTTPS\\n/api/bot/export/*" dir=back constraint=false];
N8N -> GG [label="HTTPS\\n(OAuth)" constraint=false];
Browser -> TP [label="HTTPS, виджет покупки" style=dashed constraint=false];
GH -> Nginx [xlabel="SSH, выкладка" style=dashed constraint=false lhead=cluster_ru];
GH -> N8N [label="SSH, выкладка бота" style=dashed constraint=false lhead=cluster_ext];
}}'''
open("10_architecture.dot", "w").write(dot)
subprocess.run(["dot", "-Tpng", "10_architecture.dot", "-o", "10_architecture.png"], check=True)
