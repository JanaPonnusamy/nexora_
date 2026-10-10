using System;
using System.Collections.Generic;
using System.Text;

namespace NexoraOrderManagement
{
    // Decodes (does NOT verify) a JWT's payload so the client can read its own
    // role_names / store_code / is_platform_user claims to decide whether to
    // show a store picker. Verification is the server's job on every request.
    internal static class JwtHelper
    {
        public static Dictionary<string, object> DecodePayload(string token)
        {
            try
            {
                if (string.IsNullOrEmpty(token)) return new Dictionary<string, object>();
                var parts = token.Split('.');
                if (parts.Length < 2) return new Dictionary<string, object>();
                var payload = parts[1].Replace('-', '+').Replace('_', '/');
                switch (payload.Length % 4)
                {
                    case 2: payload += "=="; break;
                    case 3: payload += "="; break;
                }
                var bytes = Convert.FromBase64String(payload);
                var json = Encoding.UTF8.GetString(bytes);
                return Json.Obj(Json.Parse(json));
            }
            catch
            {
                return new Dictionary<string, object>();
            }
        }
    }
}
