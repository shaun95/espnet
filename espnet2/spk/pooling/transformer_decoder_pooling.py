import torch
import torch.nn as nn
from typing import List, Tuple
from typeguard import check_argument_types

from espnet2.spk.pooling.abs_pooling import AbsPooling
from espnet.nets.pytorch_backend.transformer.attention import MultiHeadedAttention
from espnet.nets.pytorch_backend.transformer.decoder_layer import DecoderLayer
from espnet.nets.pytorch_backend.transformer.embedding import PositionalEncoding
from espnet.nets.pytorch_backend.transformer.layer_norm import LayerNorm
from espnet.nets.pytorch_backend.transformer.positionwise_feed_forward import (
    PositionwiseFeedForward,
)
from espnet2.asr.decoder.transformer_decoder import (
    TransformerDecoder, BaseTransformerDecoder
)
from espnet.nets.pytorch_backend.transformer.repeat import repeat

class TransformerDecoderPooling(AbsPooling, BaseTransformerDecoder):
    """
    Inputs task token as an input instead of <sos>.
    Applies cross attention with the encoder output (i.e., frame-level speaker
    embeddings).
    Designed to output different embeddings from the same input utterance when
    fed with different task tokens.

    args:

    """

    def __init__(
        self,
        vocab_size: int,
        encoder_output_size: int,
        num_blocks: int = 3,
        attention_dim: int = 512,
        attention_heads: int = 4,
        linear_units: int = 2048,
        dropout_rate: float = 0.1,
        positional_dropout_rate: float = 0.1,
        self_attention_dropout_rate: float = 0.0,
        src_attention_dropout_rate: float = 0.0,
        input_layer: str = "embed",
        pos_enc_class=PositionalEncoding,
        concat_after: bool = False,
        normalize_before: bool = True,
        use_output_layer: bool = False,
        layer_drop_rate: float = 0.0,
    ):
        assert check_argument_types()
        super().__init__(
            vocab_size=vocab_size,
            encoder_output_size=encoder_output_size,
            dropout_rate=dropout_rate,
            positional_dropout_rate=positional_dropout_rate,
            input_layer=input_layer,
            use_output_layer=use_output_layer,
            pos_enc_class=pos_enc_class,
            normalize_before=normalize_before,
        )

        if attention_dim != encoder_output_size:
            self.encoder_mapping = nn.Linear(encoder_output_size, attention_dim)
        else:
            self.encoder_mapping = nn.Identity()
        self._output_size = attention_dim

        self.decoders = repeat(
            num_blocks,
            lambda lnum: DecoderLayer(
                attention_dim,
                MultiHeadedAttention(
                    attention_heads, attention_dim, self_attention_dropout_rate
                ),
                MultiHeadedAttention(
                    attention_heads, attention_dim, src_attention_dropout_rate
                ),
                PositionwiseFeedForward(attention_dim, linear_units, dropout_rate),
                dropout_rate,
                normalize_before,
                concat_after,
            ),
            layer_drop_rate,
        )

    def output_size(self):
        return self._output_size

    def forward(
        self,
        encoder_output: torch.Tensor,
        task_tokens: torch.Tensor,
                ):
        """
        Args:
            encoder_output: frame-level embeddings, (batch, dim, seq)
            task_tokens: (batch,)
        Returns:
            x: utterance-level embedding (batch, dim_out)
        """
        #(bs, seq, dim)
        memory = self.encoder_mapping(encoder_output.transpose(-2,-1))
        print(f"memory, {memory.size()}")
        x = self.embed(task_tokens.unsqueeze(1))
        print(f"task tokens after embed, {x.size()}")

        # make masks
        x, _, memory, _ = self.decoders(
            x, None, memory, None
        )
        print(f"x, {x.size()}")
        if self.normalize_before:
            x = self.after_norm(x)

        # (bs, dim)
        return x.squeeze(1)

