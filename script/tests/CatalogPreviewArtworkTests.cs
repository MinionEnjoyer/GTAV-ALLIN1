using System;
using System.IO;
using Newtonsoft.Json.Linq;
using Xunit;
using ALLIN1.ReactorBridge;

public sealed class CatalogPreviewArtworkTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "allin1-preview-test-" + Guid.NewGuid().ToString("N"));
    private string Store(string prefix, string category, string name, bool image = true)
    {
        string folder = Path.Combine(root, "plugins", "ReactorV", "ui", "assets", "allin1", prefix + category);
        Directory.CreateDirectory(folder);
        string file = name + "." + new string('a', 64) + ".png";
        File.WriteAllText(Path.Combine(folder, "index.json"), new JObject {
            ["schema_version"] = 1,
            ["owner"] = prefix == "generated-" ? "allin1.prelaunch-previews" : "allin1.default-previews",
            ["images"] = new JObject { [name] = file }
        }.ToString());
        // Real tiny PNG fixture; the lookup only reads its signature/IHDR.
        if (image) File.WriteAllBytes(Path.Combine(folder, file), Convert.FromBase64String(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="));
        return folder;
    }

    [Theory]
    [InlineData("weapons", "weapon_pistol")]
    [InlineData("vehicles", "adder")]
    [InlineData("gear", "p_parachute_s")]
    public void GeneratedOverridesDefaultsAndMissingGeneratedUsesDefault(string category, string name)
    {
        Store("default-", category, name);
        Assert.StartsWith("assets/allin1/default-", CatalogPreviewArtwork.Read(root, category, 2048)[name.ToUpperInvariant()]);
        string generated = Store("generated-", category, name);
        Assert.StartsWith("assets/allin1/generated-", CatalogPreviewArtwork.Read(root, category, 2048)[name]);
        File.WriteAllBytes(Path.Combine(generated, name + "." + new string('a', 64) + ".png"), new byte[0]);
        Assert.StartsWith("assets/allin1/default-", CatalogPreviewArtwork.Read(root, category, 2048)[name]);
    }

    [Fact]
    public void MissingOrUnindexedArtReturnsPlaceholder()
    {
        Store("default-", "vehicles", "adder", image: false);
        Assert.Empty(CatalogPreviewArtwork.Read(root, "vehicles", 2048));
        Assert.Empty(CatalogPreviewArtwork.Read(root, "../../other", 2048));
        Assert.Empty(CatalogPreviewArtwork.Read("", "vehicles", 2048));
    }

    [Theory]
    [InlineData("{broken")]
    [InlineData("{\"schema_version\":2,\"owner\":\"allin1.prelaunch-previews\",\"images\":{}}")]
    [InlineData("{\"schema_version\":1,\"owner\":\"other-mod\",\"images\":{}}")]
    public void BadGeneratedIndexNeverHidesDefault(string json)
    {
        Store("default-", "vehicles", "adder");
        string folder = Store("generated-", "vehicles", "adder");
        File.WriteAllText(Path.Combine(folder, "index.json"), json);
        Assert.StartsWith("assets/allin1/default-", CatalogPreviewArtwork.Read(root, "vehicles", 2048)["adder"]);
    }

    [Theory]
    [InlineData("../adder.png")]
    [InlineData("https://example.com/image.png")]
    [InlineData("adder.png")]
    public void NonportableImageNamesAreIgnored(string file)
    {
        string folder = Store("default-", "vehicles", "adder");
        var index = JObject.Parse(File.ReadAllText(Path.Combine(folder, "index.json")));
        index["images"]["adder"] = file;
        File.WriteAllText(Path.Combine(folder, "index.json"), index.ToString());
        Assert.Empty(CatalogPreviewArtwork.Read(root, "vehicles", 2048));
    }

    [Fact]
    public void IndexLimitsAreEnforced()
    {
        string folder = Store("default-", "vehicles", "adder");
        Assert.Empty(CatalogPreviewArtwork.Read(root, "vehicles", 0));
        File.WriteAllText(Path.Combine(folder, "index.json"), new string(' ', 524289));
        Assert.Empty(CatalogPreviewArtwork.Read(root, "vehicles", 2048));
    }

    [Theory]
    [InlineData("invalid")]
    [InlineData("oversized")]
    [InlineData("dimensions")]
    public void DamagedGeneratedImageUsesDefault(string damage)
    {
        Store("default-", "vehicles", "adder");
        string folder = Store("generated-", "vehicles", "adder");
        string path = Path.Combine(folder, "adder." + new string('a', 64) + ".png");
        if (damage == "oversized")
        {
            using var file = File.OpenWrite(path);
            file.SetLength(4 * 1024 * 1024 + 1);
        }
        else if (damage == "dimensions")
        {
            byte[] bytes = File.ReadAllBytes(path);
            bytes[16] = 255;
            File.WriteAllBytes(path, bytes);
        }
        else File.WriteAllText(path, new string('x', 100));
        Assert.StartsWith("assets/allin1/default-", CatalogPreviewArtwork.Read(root, "vehicles", 2048)["adder"]);
    }

    public void Dispose()
    {
        if (Directory.Exists(root)) Directory.Delete(root, true);
    }
}
