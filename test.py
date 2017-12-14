import csv

_colors = []
with open('./dialog/en-us/colors.value') as f:
    colors = list(csv.reader(f))
    for color in colors:
        _colors.append(color)

for i, color in enumerate(_colors):
    _colors[i][0] = color[0].lower()

with open('./test.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerows(_colors)
