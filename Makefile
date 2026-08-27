.PHONY: install run test image deploy

IMAGE ?= my-agent
TAG ?= latest

install:
	uv sync

run:
	uv run agent

test:
	uv run pytest -q

image:
	docker build -t $(IMAGE):$(TAG) .

deploy:
	helm upgrade --install my-agent deploy/helm \
		--set image.repository=$(IMAGE) \
		--set image.tag=$(TAG)
