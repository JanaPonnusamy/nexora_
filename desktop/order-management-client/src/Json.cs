using System;
using System.Collections.Generic;
using System.Globalization;
using System.Web.Script.Serialization;

namespace NexoraOrderManagement
{
    // Thin wrapper over the in-box JavaScriptSerializer so the whole client
    // needs no vendored JSON DLL. DeserializeObject returns Dictionary<string,
    // object> for JSON objects and object[] for JSON arrays.
    internal static class Json
    {
        private static JavaScriptSerializer Ser()
        {
            var s = new JavaScriptSerializer();
            s.MaxJsonLength = int.MaxValue;   // order grids can be large
            return s;
        }

        public static object Parse(string text)
        {
            if (string.IsNullOrEmpty(text)) return null;
            return Ser().DeserializeObject(text);
        }

        public static string Write(object value)
        {
            return Ser().Serialize(value);
        }

        // JSON array -> list of row dictionaries (tolerates a single object).
        public static List<Dictionary<string, object>> Rows(object parsed)
        {
            var list = new List<Dictionary<string, object>>();
            var arr = parsed as object[];
            if (arr != null)
            {
                foreach (var item in arr)
                {
                    var d = item as Dictionary<string, object>;
                    if (d != null) list.Add(d);
                }
            }
            else
            {
                var d = parsed as Dictionary<string, object>;
                if (d != null) list.Add(d);
            }
            return list;
        }

        public static Dictionary<string, object> Obj(object parsed)
        {
            var d = parsed as Dictionary<string, object>;
            return d != null ? d : new Dictionary<string, object>();
        }

        public static string Str(Dictionary<string, object> d, string key)
        {
            object v;
            if (d != null && d.TryGetValue(key, out v) && v != null)
                return Convert.ToString(v, CultureInfo.InvariantCulture);
            return "";
        }
    }
}
