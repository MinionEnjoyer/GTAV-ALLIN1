using System;
using System.Collections.Generic;
using System.IO;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class PortableJsonParserTests
    {
        [Fact]
        public void ParsesEveryRegistryValueShape()
        {
            var root = Assert.IsType<Dictionary<string, object>>(
                PortableJsonParser.Parse(
                    "{\"text\":\"line\\n\\u263a\\ud83d\\ude80\"," +
                    "\"integer\":3,\"large\":2147483648," +
                    "\"fraction\":1.25,\"exponent\":1e2," +
                    "\"yes\":true,\"no\":false,\"none\":null," +
                    "\"array\":[1,\"two\",{}]}"));

            Assert.Equal("line\n☺🚀", root["text"]);
            Assert.IsType<int>(root["integer"]);
            Assert.IsType<long>(root["large"]);
            Assert.Equal(1.25m, root["fraction"]);
            Assert.Equal(100m, root["exponent"]);
            Assert.Equal(true, root["yes"]);
            Assert.Equal(false, root["no"]);
            Assert.Null(root["none"]);
            Assert.IsType<object[]>(root["array"]);
        }

        [Fact]
        public void DuplicateObjectMembersAreRejectedAtEveryLevel()
        {
            Assert.Throws<InvalidDataException>(() =>
                PortableJsonParser.Parse("{\"value\":1,\"value\":2}"));
            Assert.Throws<InvalidDataException>(() =>
                PortableJsonParser.Parse("{\"nested\":{\"x\":1,\"x\":2}}"));
            Assert.Throws<InvalidDataException>(() =>
                PortableJsonParser.Parse("{\"a\":1,\"\\u0061\":2}"));
        }

        [Theory]
        [InlineData("")]
        [InlineData("true false")]
        [InlineData("{'single':'quotes'}")]
        [InlineData("{\"trailing\":true,}")]
        [InlineData("[1,]")]
        [InlineData("[01]")]
        [InlineData("[+1]")]
        [InlineData("[1.]")]
        [InlineData("[.1]")]
        [InlineData("[1e]")]
        [InlineData("[NaN]")]
        [InlineData("[Infinity]")]
        [InlineData("[1e400]")]
        [InlineData("[\"bad\\xescape\"]")]
        [InlineData("[\"bad\ncontrol\"]")]
        [InlineData("[\"\\uD800\"]")]
        [InlineData("[\"\\uDC00\"]")]
        [InlineData("[\"\\uD800\\u0041\"]")]
        public void RejectsMalformedOrNonstandardJson(string json)
        {
            Assert.Throws<InvalidDataException>(() =>
                PortableJsonParser.Parse(json));
        }

        [Fact]
        public void EnforcesInputLengthAndNestingLimits()
        {
            string oversized = new string(
                ' ', PortableJsonParser.MaximumJsonLength + 1);
            Assert.Throws<InvalidDataException>(() =>
                PortableJsonParser.Parse(oversized));

            string deepestAllowed = new string(
                '[', PortableJsonParser.MaximumDepth) + "null" +
                new string(']', PortableJsonParser.MaximumDepth);
            PortableJsonParser.Parse(deepestAllowed);

            string tooDeep = "[" + deepestAllowed + "]";
            Assert.Throws<InvalidDataException>(() =>
                PortableJsonParser.Parse(tooDeep));
        }

        [Fact]
        public void RegistryRejectsDuplicateJsonKeysBeforeAuthorizationValidation()
        {
            const string json = "{\"schema_version\":1," +
                "\"schema_version\":1,\"api_version\":1,\"extensions\":[]}";

            Assert.Throws<InvalidDataException>(() =>
                RuntimeExtensionRegistry.Parse(
                    json, Path.Combine(Path.GetTempPath(), "game", "scripts")));
        }
    }
}
