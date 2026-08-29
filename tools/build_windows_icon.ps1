param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$PngOutputPath,
    [Parameter(Mandatory = $true)][string]$IcoOutputPath
)

Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies 'System.Drawing' -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;

public static class WindowsIconBuilder
{
    private static readonly int[] Sizes = { 16, 24, 32, 48, 64, 128, 256 };

    public static void Build(string inputPath, string pngOutputPath, string icoOutputPath)
    {
        using (var source = new Bitmap(inputPath))
        {
            var frames = new List<byte[]>();
            foreach (int size in Sizes)
                frames.Add(RenderPng(source, size));

            File.WriteAllBytes(pngOutputPath, frames[frames.Count - 1]);
            WriteIco(icoOutputPath, frames);
        }
    }

    private static byte[] RenderPng(Bitmap source, int size)
    {
        using (var target = new Bitmap(size, size, PixelFormat.Format32bppArgb))
        using (var graphics = Graphics.FromImage(target))
        using (var stream = new MemoryStream())
        {
            graphics.CompositingMode = CompositingMode.SourceCopy;
            graphics.CompositingQuality = CompositingQuality.HighQuality;
            graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
            graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
            graphics.SmoothingMode = SmoothingMode.HighQuality;
            graphics.Clear(Color.Transparent);

            float scale = Math.Min((float)size / source.Width, (float)size / source.Height);
            int width = Math.Max(1, (int)Math.Round(source.Width * scale));
            int height = Math.Max(1, (int)Math.Round(source.Height * scale));
            int x = (size - width) / 2;
            int y = (size - height) / 2;
            graphics.DrawImage(source, new Rectangle(x, y, width, height),
                0, 0, source.Width, source.Height, GraphicsUnit.Pixel);

            target.Save(stream, ImageFormat.Png);
            return stream.ToArray();
        }
    }

    private static void WriteIco(string path, List<byte[]> frames)
    {
        using (var stream = File.Create(path))
        using (var writer = new BinaryWriter(stream))
        {
            writer.Write((ushort)0);
            writer.Write((ushort)1);
            writer.Write((ushort)frames.Count);

            int offset = 6 + frames.Count * 16;
            for (int i = 0; i < frames.Count; i++)
            {
                int size = Sizes[i];
                writer.Write((byte)(size == 256 ? 0 : size));
                writer.Write((byte)(size == 256 ? 0 : size));
                writer.Write((byte)0);
                writer.Write((byte)0);
                writer.Write((ushort)1);
                writer.Write((ushort)32);
                writer.Write((uint)frames[i].Length);
                writer.Write((uint)offset);
                offset += frames[i].Length;
            }

            foreach (byte[] frame in frames)
                writer.Write(frame);
        }
    }
}
'@

[WindowsIconBuilder]::Build($InputPath, $PngOutputPath, $IcoOutputPath)
