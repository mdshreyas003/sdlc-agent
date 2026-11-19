// Copyright 2015 The Cockroach Authors.
//
// Use of this software is governed by the CockroachDB Software License
// included in the /LICENSE file.

// Miniature of pkg/sql/exec_util.go for the fixture history.

package sql

import (
	"github.com/cockroachdb/cockroach/pkg/settings"
	"github.com/cockroachdb/cockroach/pkg/sql/sessiondatapb"
)

var experimentalUseNewSchemaChanger = settings.RegisterEnumSetting(
	settings.ApplicationLevel,
	"sql.defaults.use_declarative_schema_changer",
	"default value for use_declarative_schema_changer session setting;"+
		"disables new schema changer by default",
	"on",
	map[sessiondatapb.NewSchemaChangerMode]string{
		sessiondatapb.UseNewSchemaChangerOff:          "off",
		sessiondatapb.UseNewSchemaChangerOn:           "on",
		sessiondatapb.UseNewSchemaChangerUnsafe:       "unsafe",
		sessiondatapb.UseNewSchemaChangerUnsafeAlways: "unsafe_always",
	},
	settings.WithPublic,
)

// SessionDefaults returns the default values for the session settings that
// this file registers.
func SessionDefaults(sv *settings.Values) map[string]string {
	return map[string]string{
		"use_declarative_schema_changer": experimentalUseNewSchemaChanger.String(sv),
	}
}
