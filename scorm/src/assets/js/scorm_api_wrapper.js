/*
 * pipwerks SCORM Wrapper — slim SCORM 1.2 / 2004 JavaScript API for browser content
 *
 * Source: https://github.com/pipwerks/scorm-api-wrapper
 * License: MIT (Philip Hutchison)
 *
 * This vendored copy trimmed for SCORM 1.2 focus. For 2004 features or the full
 * reference implementation, swap this file with the upstream build.
 *
 * Usage:
 *   pipwerks.SCORM.version = "1.2";
 *   var ok = pipwerks.SCORM.init();
 *   var status = pipwerks.SCORM.get("cmi.core.lesson_status");
 *   pipwerks.SCORM.set("cmi.core.lesson_status", "completed");
 *   pipwerks.SCORM.save();
 *   pipwerks.SCORM.quit();
 */

var pipwerks = {};
pipwerks.UTILS = {};
pipwerks.debug = { isActive: false };

pipwerks.SCORM = {
  version: null,
  handleCompletionStatus: true,
  handleExitMode: true,
  API: { handle: null, isFound: false },
  connection: { isActive: false },
  data: { completionStatus: null, exitStatus: null },
  debug: {},
};

// -------- API discovery ----------------------------------------------------

pipwerks.SCORM.API.find = function (win) {
  var API = null,
    findAttempts = 0,
    findAttemptLimit = 500,
    errorGettingAPI = "Error finding API. ",
    version = pipwerks.SCORM.version,
    traceMsgPrefix = "SCORM.API.find";

  while (
    !win.API &&
    !win.API_1484_11 &&
    win.parent &&
    win.parent != win &&
    findAttempts <= findAttemptLimit
  ) {
    findAttempts++;
    win = win.parent;
  }

  if (version) {
    switch (version) {
      case "2004":
        if (win.API_1484_11) {
          API = win.API_1484_11;
        } else {
          pipwerks.UTILS.trace(traceMsgPrefix + ": SCORM 2004 API not found.");
        }
        break;
      case "1.2":
        if (win.API) {
          API = win.API;
        } else {
          pipwerks.UTILS.trace(traceMsgPrefix + ": SCORM 1.2 API not found.");
        }
        break;
    }
  } else {
    if (win.API_1484_11) {
      pipwerks.SCORM.version = "2004";
      API = win.API_1484_11;
    } else if (win.API) {
      pipwerks.SCORM.version = "1.2";
      API = win.API;
    }
  }

  if (API) {
    pipwerks.UTILS.trace(traceMsgPrefix + ": API found. Version: " + pipwerks.SCORM.version);
  }
  return API;
};

pipwerks.SCORM.API.get = function () {
  var API = null,
    win = window;

  API = pipwerks.SCORM.API.find(win);

  if (!API && win.parent && win.parent != win) {
    API = pipwerks.SCORM.API.find(win.parent);
  }
  if (!API && win.top && win.top.opener) {
    API = pipwerks.SCORM.API.find(win.top.opener);
  }
  if (!API && win.top && win.top.opener && win.top.opener.document) {
    API = pipwerks.SCORM.API.find(win.top.opener.document);
  }

  if (API) {
    pipwerks.SCORM.API.isFound = true;
  } else {
    pipwerks.UTILS.trace("API.get failed: Can't find the API!");
  }

  return API;
};

pipwerks.SCORM.API.getHandle = function () {
  var API = pipwerks.SCORM.API;
  if (!API.handle && !API.isFound) {
    API.handle = API.get();
  }
  return API.handle;
};

// -------- Connection management --------------------------------------------

pipwerks.SCORM.connection.initialize = function () {
  var API = pipwerks.SCORM.API.getHandle(),
    errorCode = 0,
    success = false;
  if (API) {
    switch (pipwerks.SCORM.version) {
      case "1.2":
        success = this.toBoolean(API.LMSInitialize(""));
        break;
      case "2004":
        success = this.toBoolean(API.Initialize(""));
        break;
    }
    if (success) {
      errorCode = pipwerks.SCORM.data.errorCode = 0;
      pipwerks.SCORM.connection.isActive = true;
    } else {
      errorCode = pipwerks.SCORM.debug.getCode();
      pipwerks.UTILS.trace("connection.initialize failed. errorCode: " + errorCode);
    }
  } else {
    pipwerks.UTILS.trace("connection.initialize failed: API is null.");
  }
  return success;
};

pipwerks.SCORM.connection.terminate = function () {
  var success = false,
    API = pipwerks.SCORM.API.getHandle();
  if (API && pipwerks.SCORM.connection.isActive) {
    switch (pipwerks.SCORM.version) {
      case "1.2":
        success = this.toBoolean(API.LMSFinish(""));
        break;
      case "2004":
        success = this.toBoolean(API.Terminate(""));
        break;
    }
    if (success) {
      pipwerks.SCORM.connection.isActive = false;
    }
  }
  return success;
};

pipwerks.SCORM.connection.toBoolean = function (v) {
  switch (typeof v) {
    case "object":
    case "string":
      return /(true|1)/i.test(v);
    case "number":
      return !!v;
    case "boolean":
      return v;
    case "undefined":
      return null;
    default:
      return false;
  }
};

// -------- Data get/set/save -----------------------------------------------

pipwerks.SCORM.data.get = function (parameter) {
  var value = null,
    API = pipwerks.SCORM.API.getHandle();
  if (API && pipwerks.SCORM.connection.isActive) {
    switch (pipwerks.SCORM.version) {
      case "1.2":
        value = API.LMSGetValue(parameter);
        break;
      case "2004":
        value = API.GetValue(parameter);
        break;
    }
  }
  return value;
};

pipwerks.SCORM.data.set = function (parameter, value) {
  var success = false,
    API = pipwerks.SCORM.API.getHandle();
  if (API && pipwerks.SCORM.connection.isActive) {
    switch (pipwerks.SCORM.version) {
      case "1.2":
        success = pipwerks.SCORM.connection.toBoolean(API.LMSSetValue(parameter, value));
        break;
      case "2004":
        success = pipwerks.SCORM.connection.toBoolean(API.SetValue(parameter, value));
        break;
    }
  }
  return success;
};

pipwerks.SCORM.data.save = function () {
  var success = false,
    API = pipwerks.SCORM.API.getHandle();
  if (API && pipwerks.SCORM.connection.isActive) {
    switch (pipwerks.SCORM.version) {
      case "1.2":
        success = pipwerks.SCORM.connection.toBoolean(API.LMSCommit(""));
        break;
      case "2004":
        success = pipwerks.SCORM.connection.toBoolean(API.Commit(""));
        break;
    }
  }
  return success;
};

// -------- Debug / error surface --------------------------------------------

pipwerks.SCORM.debug.getCode = function () {
  var API = pipwerks.SCORM.API.getHandle(),
    code = 0;
  if (API) {
    switch (pipwerks.SCORM.version) {
      case "1.2":
        code = parseInt(API.LMSGetLastError(), 10);
        break;
      case "2004":
        code = parseInt(API.GetLastError(), 10);
        break;
    }
  }
  return code;
};

// -------- Convenience facade ----------------------------------------------
//
// Bind each alias to the owning sub-object so ``this`` inside the
// underlying method (e.g. ``this.toBoolean`` inside ``connection.initialize``)
// keeps resolving to ``pipwerks.SCORM.connection``. Without the bind,
// calling ``pipwerks.SCORM.init()`` via the alias makes ``this`` be
// ``pipwerks.SCORM`` which does not define ``toBoolean``, and the call
// throws ``TypeError: this.toBoolean is not a function`` the moment any
// LMS API response needs to be coerced to a boolean.

pipwerks.SCORM.init = pipwerks.SCORM.connection.initialize.bind(pipwerks.SCORM.connection);
pipwerks.SCORM.get = pipwerks.SCORM.data.get.bind(pipwerks.SCORM.data);
pipwerks.SCORM.set = pipwerks.SCORM.data.set.bind(pipwerks.SCORM.data);
pipwerks.SCORM.save = pipwerks.SCORM.data.save.bind(pipwerks.SCORM.data);
pipwerks.SCORM.quit = pipwerks.SCORM.connection.terminate.bind(pipwerks.SCORM.connection);

pipwerks.UTILS.trace = function (msg) {
  if (pipwerks.debug.isActive) {
    if (window.console && window.console.log) {
      window.console.log(msg);
    }
  }
};
