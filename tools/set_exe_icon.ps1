param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$IconPath
)

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;

public static class ExecutableIconWriter
{
    private const uint LOAD_LIBRARY_AS_DATAFILE = 0x00000002;
    private static readonly IntPtr RT_ICON = (IntPtr)3;
    private static readonly IntPtr RT_GROUP_ICON = (IntPtr)14;

    private delegate bool EnumResNameProc(IntPtr module, IntPtr type, IntPtr name, IntPtr param);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryEx(string fileName, IntPtr file, uint flags);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool FreeLibrary(IntPtr module);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool EnumResourceNames(IntPtr module, IntPtr type, EnumResNameProc callback, IntPtr param);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr BeginUpdateResource(string fileName, bool deleteExistingResources);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool UpdateResource(IntPtr update, IntPtr type, IntPtr name, ushort language, byte[] data, uint size);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool EndUpdateResource(IntPtr update, bool discard);

    public static void Set(string exePath, string iconPath)
    {
        List<ushort> groupIds = FindGroupIds(exePath);
        if (groupIds.Count == 0)
            groupIds.Add(1);

        byte[] ico = File.ReadAllBytes(iconPath);
        ushort count = BitConverter.ToUInt16(ico, 4);
        var images = new List<byte[]>();
        var iconIds = new List<ushort>();
        for (int i = 0; i < count; i++)
        {
            int entry = 6 + i * 16;
            int length = BitConverter.ToInt32(ico, entry + 8);
            int offset = BitConverter.ToInt32(ico, entry + 12);
            byte[] image = new byte[length];
            Buffer.BlockCopy(ico, offset, image, 0, length);
            images.Add(image);
            iconIds.Add((ushort)(201 + i));
        }

        IntPtr update = BeginUpdateResource(exePath, false);
        if (update == IntPtr.Zero)
            ThrowLastError("BeginUpdateResource");

        bool success = false;
        try
        {
            for (int i = 0; i < images.Count; i++)
            {
                if (!UpdateResource(update, RT_ICON, (IntPtr)iconIds[i], 0, images[i], (uint)images[i].Length))
                    ThrowLastError("UpdateResource icon");
            }

            byte[] group = BuildGroup(ico, iconIds);
            foreach (ushort groupId in groupIds)
            {
                if (!UpdateResource(update, RT_GROUP_ICON, (IntPtr)groupId, 0, group, (uint)group.Length))
                    ThrowLastError("UpdateResource group");
            }
            success = true;
        }
        finally
        {
            if (!EndUpdateResource(update, !success) && success)
                ThrowLastError("EndUpdateResource");
        }
    }

    private static List<ushort> FindGroupIds(string exePath)
    {
        var ids = new List<ushort>();
        IntPtr module = LoadLibraryEx(exePath, IntPtr.Zero, LOAD_LIBRARY_AS_DATAFILE);
        if (module == IntPtr.Zero)
            return ids;
        try
        {
            EnumResourceNames(module, RT_GROUP_ICON, delegate(IntPtr m, IntPtr t, IntPtr name, IntPtr p)
            {
                long value = name.ToInt64();
                if ((value >> 16) == 0)
                    ids.Add((ushort)value);
                return true;
            }, IntPtr.Zero);
        }
        finally
        {
            FreeLibrary(module);
        }
        return ids;
    }

    private static byte[] BuildGroup(byte[] ico, List<ushort> iconIds)
    {
        ushort count = BitConverter.ToUInt16(ico, 4);
        using (var stream = new MemoryStream())
        using (var writer = new BinaryWriter(stream))
        {
            writer.Write((ushort)0);
            writer.Write((ushort)1);
            writer.Write(count);
            for (int i = 0; i < count; i++)
            {
                int entry = 6 + i * 16;
                writer.Write(ico[entry]);
                writer.Write(ico[entry + 1]);
                writer.Write(ico[entry + 2]);
                writer.Write(ico[entry + 3]);
                writer.Write(BitConverter.ToUInt16(ico, entry + 4));
                writer.Write(BitConverter.ToUInt16(ico, entry + 6));
                writer.Write(BitConverter.ToUInt32(ico, entry + 8));
                writer.Write(iconIds[i]);
            }
            return stream.ToArray();
        }
    }

    private static void ThrowLastError(string operation)
    {
        throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), operation);
    }
}
'@

[ExecutableIconWriter]::Set($ExePath, $IconPath)
