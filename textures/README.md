# 棋子贴图

默认使用程序绘制的圆形棋子。支持 PNG / GIF 图片，建议透明背景、48×48 像素。

在主目录 config.json 的 textures 字段设置对应文件名，例如：

```json
"textures": {"red_R": "red_rook.png", "black_K": "black_king.png"}
```

键名为 red_ 或 black_ 加棋子代码：P兵、C炮、R车、N马、B象、A士、K真将、F假将。
敌方看到的假将使用真将图片。图片缺失或无法读取时回退为文字棋子。
