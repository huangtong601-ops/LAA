param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies 'System.Drawing' -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

public static class CheckerboardAlpha
{
    public static void Remove(string inputPath, string outputPath)
    {
        using (var source = new Bitmap(inputPath))
        using (var rgb = new Bitmap(source.Width, source.Height, PixelFormat.Format24bppRgb))
        {
            using (var graphics = Graphics.FromImage(rgb))
            {
                graphics.DrawImageUnscaled(source, 0, 0);
            }

            int width = rgb.Width;
            int height = rgb.Height;
            var rect = new Rectangle(0, 0, width, height);
            var data = rgb.LockBits(rect, ImageLockMode.ReadOnly, PixelFormat.Format24bppRgb);
            byte[] pixels = new byte[Math.Abs(data.Stride) * height];
            Marshal.Copy(data.Scan0, pixels, 0, pixels.Length);
            rgb.UnlockBits(data);

            int count = width * height;
            var candidate = new byte[count];
            var visited = new byte[count];
            var transparent = new byte[count];
            var queue = new int[count];

            for (int y = 0; y < height; y++)
            {
                int row = y * data.Stride;
                for (int x = 0; x < width; x++)
                {
                    int p = row + x * 3;
                    int b = pixels[p];
                    int g = pixels[p + 1];
                    int r = pixels[p + 2];
                    int min = Math.Min(r, Math.Min(g, b));
                    int max = Math.Max(r, Math.Max(g, b));
                    if (min >= 236 && max - min <= 16)
                        candidate[y * width + x] = 1;
                }
            }

            for (int start = 0; start < count; start++)
            {
                if (candidate[start] == 0 || visited[start] != 0)
                    continue;

                int head = 0;
                int tail = 0;
                queue[tail++] = start;
                visited[start] = 1;

                while (head < tail)
                {
                    int current = queue[head++];
                    int x = current % width;
                    int y = current / width;
                    Visit(current - 1, x > 0, candidate, visited, queue, ref tail);
                    Visit(current + 1, x + 1 < width, candidate, visited, queue, ref tail);
                    Visit(current - width, y > 0, candidate, visited, queue, ref tail);
                    Visit(current + width, y + 1 < height, candidate, visited, queue, ref tail);
                }

                if (tail >= 96)
                {
                    for (int i = 0; i < tail; i++)
                        transparent[queue[i]] = 1;
                }
            }

            for (int pass = 0; pass < 2; pass++)
            {
                var expanded = (byte[])transparent.Clone();
                for (int y = 1; y < height - 1; y++)
                {
                    int row = y * data.Stride;
                    for (int x = 1; x < width - 1; x++)
                    {
                        int index = y * width + x;
                        if (transparent[index] != 0)
                            continue;
                        if (transparent[index - 1] == 0 && transparent[index + 1] == 0 &&
                            transparent[index - width] == 0 && transparent[index + width] == 0)
                            continue;

                        int p = row + x * 3;
                        int b = pixels[p];
                        int g = pixels[p + 1];
                        int r = pixels[p + 2];
                        int min = Math.Min(r, Math.Min(g, b));
                        int max = Math.Max(r, Math.Max(g, b));
                        if (min >= 218 && max - min <= 22)
                            expanded[index] = 1;
                    }
                }
                transparent = expanded;
            }

            using (var output = new Bitmap(width, height, PixelFormat.Format32bppArgb))
            {
                var outputData = output.LockBits(rect, ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
                byte[] rgba = new byte[Math.Abs(outputData.Stride) * height];
                for (int y = 0; y < height; y++)
                {
                    int sourceRow = y * data.Stride;
                    int outputRow = y * outputData.Stride;
                    for (int x = 0; x < width; x++)
                    {
                        int sourcePixel = sourceRow + x * 3;
                        int outputPixel = outputRow + x * 4;
                        rgba[outputPixel] = pixels[sourcePixel];
                        rgba[outputPixel + 1] = pixels[sourcePixel + 1];
                        rgba[outputPixel + 2] = pixels[sourcePixel + 2];
                        rgba[outputPixel + 3] = transparent[y * width + x] != 0 ? (byte)0 : (byte)255;
                    }
                }
                Marshal.Copy(rgba, 0, outputData.Scan0, rgba.Length);
                output.UnlockBits(outputData);
                output.Save(outputPath, ImageFormat.Png);
            }
        }
    }

    private static void Visit(int index, bool valid, byte[] candidate, byte[] visited, int[] queue, ref int tail)
    {
        if (!valid || candidate[index] == 0 || visited[index] != 0)
            return;
        visited[index] = 1;
        queue[tail++] = index;
    }
}
'@

[CheckerboardAlpha]::Remove($InputPath, $OutputPath)
