// Copyright 2021 The Cockroach Authors.
//
// Use of this software is governed by the CockroachDB Software License
// included in the /LICENSE file.

// Miniature of pkg/sql/schemachanger/scbuild/build.go for the fixture history.

package scbuild

import (
	"context"

	"github.com/cockroachdb/cockroach/pkg/sql/schemachanger/scpb"
	"github.com/cockroachdb/cockroach/pkg/sql/sem/tree"
)

// Build constructs a new state from an initial state and a statement.
func Build(ctx context.Context, initial scpb.CurrentState, stmt tree.Statement) (scpb.CurrentState, error) {
	bs := newBuilderState(ctx, initial)
	bs.buildStatement(stmt)
	return bs.output(), nil
}

type builderState struct {
	ctx     context.Context
	current scpb.CurrentState
}

func newBuilderState(ctx context.Context, initial scpb.CurrentState) *builderState {
	return &builderState{ctx: ctx, current: initial}
}

func (b *builderState) buildStatement(stmt tree.Statement) {}

func (b *builderState) output() scpb.CurrentState {
	return b.current
}
